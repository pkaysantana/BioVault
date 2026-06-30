# BioVault — Architecture

## Overview

BioVault is a deterministic, LLM-free capability enforcement layer that sits between AI science agents and the artifact store. The model — any open-weight runtime — is outside the enforcement boundary. It only sees content the gate has already authorised.

### Biotech scenario

The demo domain is pharmaceutical R&D. An AI science agent is given access to a corpus of source artifacts:

- **Public target biology paper** — published, unrestricted
- **Internal SAR table** — structure-activity relationship data; internal sensitivity
- **Docking report** — computational chemistry results
- **Toxicity report** — GLP safety study data; restricted
- **CRO assay report** — external partner data
- **Adverse-event memo** — safety signal; confidential
- **Board update** — internal summary
- **Phase II readiness memo** — derived from all of the above; confidential

The agent derives the Phase II readiness memo from four source documents. Each source document may later be revoked (e.g. data integrity finding on the adverse-event memo, or a retraction of the SAR table). BioVault ensures that the derived memo is immediately quarantined when any included source is revoked — without requiring a role change, a policy re-evaluation, or a model-based decision.

---

## BasedAI Track Alignment

BioVault is built for the **BasedAI Enterprise Memory Governance at Scale** track. The specific track requirements it addresses:

| BasedAI Requirement | BioVault Implementation | Test / Code Evidence |
|---|---|---|
| Agent-level memory governance | Capability grants scoped to `(principal, artifact, operation)` — narrower than any group or role | `test_allow_deny_matrix` |
| Sensitive data isolation | Fernet-encrypted content at rest; decrypted only after a passing permission check | `GET /artifacts/{id}` endpoint |
| Auditability of every access | `log_audit()` records `request_id`, `principal_id`, decision, reason, `latency_ms`, and structured `detail` JSON | `test_audit_records_all_operation_types` |
| Lineage tracking | `lineage_edges` stores parent IDs, `source_hash`, `inclusion` (included/redacted), `dependency_type`, `reason` | `GET /lineage/{id}` |
| Revocation propagation | BFS quarantine of all active derived descendants when a source artifact is revoked | `test_multi_level_revocation_propagation` |
| No LLM in the governance path | `evaluate_access()` is pure SQL + Python; no model import exists in `backend/app/main.py` | code inspection: zero model imports |
| Sub-200ms governance latency | Indexed SQLite lookups; P99 measured live via `GET /metrics/permission-latency` | `test_permission_latency_p99_under_200ms` |

---

## Request flow

```
Open-weight model (Qwen / Llama 3 / Mistral / Phi / GLM / BGE / E5 / Nomic …)
│
│  Tool call or REST call:
│  POST /query  { "artifact_id": "phase2_readiness_memo", "purpose": "generate_summary" }
│  Authorization: Bearer <plaintext_capability_token>
│
▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI  (:8000)                                                        │
│                                                                          │
│  1. resolve_principal()                                                  │
│     └─ hash bearer token (SHA-256)                                       │
│     └─ look up principal_id in users.token_hash                          │
│     └─ HTTP 401 if not found — no fallback, no ?user_id= override        │
│                                                                          │
│  2. evaluate_access(principal_id, artifact_id, "read")                   │
│     ├─ artifact exists?                            → no  → deny          │
│     ├─ artifact.status in (active, redacted)?      → no  → deny          │
│     ├─ has_grant(principal, artifact, "read")?     → no  → deny          │
│     └─ artifact.type == "derived"?                                       │
│         ├─ for each included parent in lineage_edges:                    │
│         │   └─ parent.status in (revoked, quarantined)? → deny           │
│         └─ (redacted artifact: only included parents checked)            │
│                                                                          │
│  3. log_audit()                                                          │
│     └─ timestamp, principal_id, artifact_id, operation                   │
│     └─ decision (allow / deny), reason, latency_ms                       │
│     └─ request_id (UUID), structured detail JSON                         │
│                                                                          │
│  4. If decision == allow:                                                │
│     └─ Fernet.decrypt(artifact.encrypted_content)                        │
│     └─ return { decision, plaintext_content, title, sensitivity, … }     │
│                                                                          │
│  5. If decision == deny:                                                 │
│     └─ return { decision, reason, request_id }  — no content             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
│
▼
Agent receives response.
If allow → pass plaintext_content as context to the model.
If deny  → do NOT call the model with this artifact; surface the denial to the user.
│
▼
Open-weight model generates output using only authorised context.
```

---

## Database schema

```
users
  id            TEXT  PRIMARY KEY
  name          TEXT
  role          TEXT
  team          TEXT
  token_hash    TEXT  UNIQUE    ← SHA-256 of bearer token; plaintext never stored

artifacts
  id            TEXT  PRIMARY KEY
  title         TEXT
  type          TEXT  (source | derived)
  sensitivity   TEXT  (public | internal | restricted | confidential)
  status        TEXT  (active | revoked | quarantined | redacted)
  encrypted_content BLOB
  created_by    TEXT  REFERENCES users(id)
  created_at    TEXT

capability_grants
  id            TEXT  PRIMARY KEY
  user_id       TEXT  REFERENCES users(id)
  artifact_id   TEXT  REFERENCES artifacts(id)
  operation     TEXT  CHECK (operation IN ('read','derive','revoke','grant','redact'))
  revoked       INT   DEFAULT 0
  expires_at    TEXT  NULLABLE
  grant_id      TEXT
  issuer_id     TEXT
  subject       TEXT
  scope         TEXT
  purpose       TEXT
  request_id    TEXT
  granted_at    TEXT

lineage_edges
  parent_artifact_id  TEXT  REFERENCES artifacts(id)
  child_artifact_id   TEXT  REFERENCES artifacts(id)
  dependency_type     TEXT
  inclusion           TEXT  (included | redacted)
  source_hash         TEXT  ← SHA-256 of parent content at derivation time
  created_by          TEXT  REFERENCES users(id)
  reason              TEXT

audit_events
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  timestamp     TEXT
  user_id       TEXT
  artifact_id   TEXT
  operation     TEXT
  decision      TEXT  (allow | deny)
  reason        TEXT
  latency_ms    REAL
  request_id    TEXT
  detail        TEXT  (JSON blob)

redaction_attestations
  artifact_id   TEXT  PRIMARY KEY  REFERENCES artifacts(id)
  created_by    TEXT
  created_at    TEXT
  reason        TEXT
  source_hashes TEXT  (JSON array of SHA-256 hashes)
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_grants_lookup
  ON capability_grants (user_id, artifact_id, operation);

CREATE INDEX IF NOT EXISTS idx_lineage_parent
  ON lineage_edges (parent_artifact_id);

CREATE INDEX IF NOT EXISTS idx_lineage_child
  ON lineage_edges (child_artifact_id);

CREATE INDEX IF NOT EXISTS idx_audit_ts
  ON audit_events (timestamp);

CREATE INDEX IF NOT EXISTS idx_token_hash
  ON users (token_hash);
```

---

## Security boundary diagram

```
 ┌─────────────────────────────────────────────────────────────┐
 │  OUTSIDE the enforcement boundary                           │
 │                                                             │
 │   ┌─────────────────────────────────────────────────────┐   │
 │   │  Open-weight model runtime                          │   │
 │   │  (Qwen, Llama, Mistral, GLM, BGE, E5, Nomic, …)    │   │
 │   │                                                     │   │
 │   │  Calls POST /query to retrieve authorised context.  │   │
 │   │  Generates a response from that context only.       │   │
 │   │  Cannot access any artifact that was denied.        │   │
 │   └───────────────────┬─────────────────────────────────┘   │
 │                       │ POST /query                         │
 └───────────────────────┼─────────────────────────────────────┘
                         │
 ┌───────────────────────▼─────────────────────────────────────┐
 │  INSIDE the enforcement boundary                            │
 │                                                             │
 │   resolve_principal → evaluate_access → log_audit           │
 │                                                             │
 │   Deterministic. No model call. No probabilistic path.      │
 │   LLM cannot influence whether access is granted.           │
 └─────────────────────────────────────────────────────────────┘
```

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Capability per `(principal, artifact, operation)` | Minimise blast radius — no wildcard grants |
| SHA-256 token hash only stored | Eliminates token leakage via DB read |
| Lineage integrity on every read | Ensures revocation effect is felt at read time, not just derivation time |
| BFS quarantine on revoke | O(n) where n is number of descendants; acceptable for typical artifact graph sizes |
| SQLite for demo | Zero-infrastructure; replace with PostgreSQL for production concurrency |
| No model in permission path | Permission decisions must be auditable, reproducible, and deterministic |
| `POST /query` as model gate | Single choke point; all agent access goes through the same enforcement stack |
| Governed redaction | Prevents redaction from being used as a bypass around parent capability checks |

---

## Open-weight model integration

Any model that supports tool calling or a REST fetch in its agentic loop can integrate with BioVault:

```python
import httpx

def retrieve_artifact(artifact_id: str, capability_token: str) -> dict:
    """Call the BioVault gate before passing content to the model."""
    r = httpx.post(
        "http://localhost:8000/query",
        json={"artifact_id": artifact_id, "purpose": "agent_retrieval"},
        headers={"Authorization": f"Bearer {capability_token}"},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()

# In the agent loop:
result = retrieve_artifact("phase2_readiness_memo", token)
if result["decision"] == "allow":
    context = result["plaintext_content"]
    # pass context to model.generate(...)
else:
    # surface denial to user; do not call model with this artifact
    print(f"Access denied: {result['reason']} ({result['request_id']})")
```

The capability token is issued at seed time (`POST /seed`) or via a grant (`POST /artifacts/{id}/grant`) and is passed to the agent by the platform layer. The model itself never holds or manages tokens.
