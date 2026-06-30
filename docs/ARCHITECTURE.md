# BioVault — Architecture

## Overview

BioVault is a deterministic, LLM-free capability enforcement layer that sits between AI agents and a shared artifact store. The model — any open-weight runtime — is outside the enforcement boundary. It only sees content the gate has already authorised.

BioVault ships with two demo scenarios:

- **SME / company-memory** (default): Payroll-leakage prevention. A marketing AI agent asks for Q3 cost data and must not receive a derived margin report that includes payroll-sensitive lineage.
- **Biotech / AI science** (secondary): Pharma R&D. An AI science agent derives a Phase II readiness memo; when the adverse-event source is revoked for data integrity reasons, the derived memo and all its children are quarantined.

Both scenarios use the same permission engine, the same lineage model, and the same audit infrastructure. The difference is only the seeded dataset.

---

## Why this is not secure RAG with role labels

RAG with LLM-based sensitivity filtering:
- Makes every retrieval go through a model to classify the content
- Token-heavy: every retrieval consumes model tokens
- Non-deterministic: the model can be confused, jailbroken, or prompted into surfacing sensitive context
- Has no concept of artifact lineage: revoking a source document does not automatically close access to derived outputs

BioVault's permission path:
- Pure SQL — deterministic, reproducible, auditable
- **Zero model tokens consumed in the permission path**
- Lineage-aware: revoking a source quarantines all derived descendants via BFS propagation
- Every decision logged with a structured `request_id` for traceability

---

## Why global memory avoids duplicated-silo drift

The alternative approach — copying files into per-team folders — breaks governance:

1. Finance copies the payroll register into a "shared" folder for the analyst.
2. The original is revoked. The copy persists. Governance sees only the original.
3. The analyst's AI agent retrieves the copy. Payroll data leaks.

BioVault uses one canonical store. Every team reads the same artifact under their own capability grant. No copies means no drift. Revoking the payroll register propagates through lineage to every derived artifact that included it — through one BFS traversal on one graph, not by chasing copies.

---

## SME scenario: principals and artifacts

### Principals

| ID | Name | Role | Capability grants |
|---|---|---|---|
| `u_owner` | Alex Kim | Owner | All ops on all artifacts |
| `u_finance` | Jordan Lee | Finance Lead | `read` on payroll register, Q3 report, handbook |
| `u_marketing` | Morgan Chen | Marketing Manager | `read` on campaign costs, vendor contracts, customer feedback, handbook |
| `u_hr` | Riley Park | HR Lead | `read` on payroll register, handbook |
| `u_ops` | Sam Rivera | Operations Manager | `read` on vendor contracts, handbook |
| `u_contractor` | Casey Jones | External Contractor | `read` on handbook only |

### Artifacts

| ID | Title | Type | Sensitivity |
|---|---|---|---|
| `campaign_cost_summary` | Campaign Cost Summary | source | internal |
| `vendor_contracts` | Vendor Contracts | source | internal |
| `payroll_salary_register` | Payroll Salary Register | source | confidential |
| `shared_customer_feedback` | Customer Feedback Digest | source | internal |
| `company_handbook` | Company Handbook | source | public |
| `q3_growth_margin_report` | Q3 Growth Margin Report | **derived** | confidential |

### Lineage

```
campaign_cost_summary ──┐
vendor_contracts      ──┼──► q3_growth_margin_report
payroll_salary_register─┘
```

The leakage case: Marketing has `read` on `campaign_cost_summary` and `vendor_contracts` individually, but lacks a capability grant on `q3_growth_margin_report`. Even if Marketing could enumerate sources, they cannot read the governed derived artifact that synthesises those sources with payroll data.

Payroll revocation propagates to `q3_growth_margin_report` through lineage — Finance is also denied after revocation.

---

## Biotech scenario: principals and artifacts (secondary)

### Principals

| ID | Name | Role | Capability grants |
|---|---|---|---|
| `u_ceo` | Avery Chen | CEO | All ops on all artifacts |
| `u_regulatory` | Nora Singh | Regulatory Lead | `read` on toxicity report, adverse-event memo, Phase II memo |
| `u_research` | Maya Patel | Research Scientist | `read`+`derive` on public paper, SAR table, docking report, toxicity report |
| `u_compchem` | Leo Morgan | Computational Chemist | `read`+`derive` on public paper, SAR table, docking report |
| `u_cro` | Owen Brooks | External CRO Scientist | `read` on public paper, CRO assay report |
| `u_intern` | Iris Lopez | Intern | `read` on public paper only |

### Lineage

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo ──► (exec brief — derived in demo)
toxicity_report     ──┤
adverse_event_memo  ──┘
```

Revoking `adverse_event_memo` quarantines `phase2_readiness_memo` and every artifact derived from it.

---

## Request flow

```
Agent runtime (any model)
│
│  POST /query  { "artifact_id": "q3_growth_margin_report", "purpose": "agent_retrieval" }
│  Authorization: Bearer <capability_token>
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
If deny  → do NOT call the model with this artifact; surface denial to user.
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

lineage_edges
  parent_artifact_id  TEXT  REFERENCES artifacts(id)
  child_artifact_id   TEXT  REFERENCES artifacts(id)
  dependency_type     TEXT
  inclusion           TEXT  (included | redacted)
  source_hash         TEXT  ← SHA-256 of parent content at derivation time
  created_by          TEXT  REFERENCES users(id)
  reason              TEXT

audit_events
  id            TEXT  PRIMARY KEY
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
  detail        TEXT  (JSON blob — source_hashes, included, redacted parents)
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

CREATE INDEX IF NOT EXISTS idx_users_token
  ON users (token_hash);
```

---

## Security boundary diagram

```
 ┌─────────────────────────────────────────────────────────────┐
 │  OUTSIDE the enforcement boundary                           │
 │                                                             │
 │   ┌─────────────────────────────────────────────────────┐   │
 │   │  Agent / model runtime                              │   │
 │   │  (any open-weight model: Qwen, Llama, Mistral, …)  │   │
 │   │                                                     │   │
 │   │  Calls POST /query to retrieve authorised context.  │   │
 │   │  Generates a response from that context only.       │   │
 │   │  Cannot access any artifact that was denied.        │   │
 │   │  Does NOT influence the permission decision.        │   │
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
 │   0 model tokens consumed. Sub-millisecond. Audited.        │
 └─────────────────────────────────────────────────────────────┘
```

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Capability per `(principal, artifact, operation)` | Minimise blast radius — no wildcard grants |
| SHA-256 token hash only stored | Eliminates token leakage via DB read |
| Lineage integrity on every read | Ensures revocation effect is felt at read time, not just derivation time |
| BFS quarantine on revoke | O(n) where n is number of descendants; consistent regardless of depth |
| Scenario-aware seeding via `?scenario=` | Same permission engine; different artifact graph demonstrates generality |
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

# SME example — Marketing agent asks for the Q3 report:
result = retrieve_artifact("q3_growth_margin_report", marketing_token)
if result["decision"] == "allow":
    context = result["plaintext_content"]
    # pass context to model.generate(...)
else:
    # surface denial to user; do not call model with this artifact
    print(f"Access denied: {result['reason']} ({result['request_id']})")
    # reason: "missing_capability_grant" (or "derived_from_revoked_source" after payroll revocation)
```

The capability token is issued at seed time (`POST /seed?scenario=sme`) or via a grant (`POST /artifacts/{id}/grant`) and is passed to the agent by the platform layer. The model itself never holds or manages tokens.
