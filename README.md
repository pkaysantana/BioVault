# BioVault

BioVault is a capability-secured artifact memory layer for AI science agents, built for the
**BasedAI Enterprise Memory Governance at Scale** track.

It demonstrates how a multi-user workspace can prevent AI agent–created artifacts from leaking
sensitive source data. The demo domain is biotech R&D: SAR data, toxicity reports, CRO assay
reports, adverse-event memos, regulatory notes, and Phase II readiness summaries.

> **Classification:** Educational prototype / hackathon MVP. Not validated scientific logic,
> clinical decision support, or a regulated medical device.

---

## What It Demonstrates

| Capability | Detail |
|---|---|
| Capability-based access | Artifact-level grants, not role-based policies |
| Deterministic permission engine | `evaluate_access()` — no LLM in the access path |
| Encrypted artifact storage | Fernet symmetric encryption (demo key — not production-safe) |
| Lineage graph | Derived artifacts trace back to every source |
| Revocation propagation | Revoking a source quarantines all downstream derived artifacts |
| Audit log | Every access attempt records user, artifact, operation, decision, reason, latency |
| Permission latency metrics | Mean, median, p95, p99 over all audit events |

---

## Architecture

```
Browser (React/Vite :5173)
    │  REST JSON  +  Authorization: Bearer <capability_token>
    ▼
FastAPI app (:8000)
    │  resolve_principal()  — hashes token, resolves principal (NEVER trusts user_id)
    │  evaluate_access()    — deterministic, synchronous, no LLM
    │  log_audit()          — request_id + structured detail
    ▼
SQLite  biovault.db
    tables: users (+token_hash), artifacts, capability_grants,
            lineage_edges (+inclusion/source_hash/reason),
            audit_events (+request_id/detail), redaction_attestations
    indexes: grant lookup, lineage parent/child, audit timestamp, token lookup
```

### The Trust Boundary (capability-bound access)

The security boundary lives in the **retrieval layer**, not the UI. A caller cannot assert an
identity — identity is proven by a bearer **capability token**:

- Each principal is issued a random token at seed time; **only the SHA-256 hash is stored**.
- Plaintext tokens are returned **once** (from `POST /seed`) for demo use.
- `resolve_principal()` is a FastAPI dependency that reads `Authorization: Bearer <token>`, hashes
  it, and resolves the owning principal. A `?user_id=` query param has **no authority**.
- `POST /artifacts/{id}/grant` requires the issuer to hold a `grant` (delegate) capability on the
  artifact, and logs `grant_id`, `issuer`, `subject`, `scope`, `purpose`, and `request_id`.

### Permission Logic

`evaluate_access(conn, principal_id, artifact_id, operation)` allows access when **all** hold:

1. Principal (resolved from token) exists.
2. Artifact exists.
3. Artifact status is `active` or `redacted`.
4. Principal holds a non-revoked, non-expired capability grant for the operation.
5. Lineage integrity:
   - **Non-redacted derived artifact** — deny if any transitive source is `revoked`/`quarantined`.
   - **Redacted derived artifact** — deny only if an *included* parent is `revoked`/`quarantined`;
     parents redacted out (content attested-removed) are excluded from the check.

Deterministic and LLM-free: no model call occurs anywhere in the permission path.

### Governed Redaction

Redaction is a privileged, attested operation — **not** a bypass around parent permissions or a way
to launder revoked data:

- `POST /derive` with `redacted=true` requires a `redact` capability on **every** parent.
- Redaction from a `revoked`/`quarantined` source is denied (`cannot_redact_revoked_source`).
- A **redaction attestation** records who, when, why, which parents were included vs. redacted, and
  per-source content hashes.
- Each lineage edge stores metadata: `source_hash`, `dependency_type`, `inclusion`
  (`included`/`redacted`), `created_by`, and `reason`.

### Revocation

When a source artifact is revoked:

- Its status is set to `revoked` and its capability grants are revoked.
- Every downstream derived artifact with status `active` is set to `quarantined` (multi-level).
- An audit event is written for the revocation and for each quarantined artifact.
- Future reads of quarantined artifacts deny with reason `derived_from_revoked_source`.

---

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Endpoints

All artifact operations require `Authorization: Bearer <capability_token>` (or `?token=` for
curl/Swagger). A `user_id` query param is ignored for authority.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| POST | `/seed` | — | Reset dataset; returns plaintext principal tokens once |
| GET | `/users` | — | List users (no tokens) |
| GET | `/artifacts` | — | List artifacts (no content) |
| GET | `/artifacts/{id}` | token | Read artifact — permission check + audit event |
| POST | `/artifacts/{id}/grant` | token | Grant a capability (issuer needs grant authority) |
| POST | `/artifacts/{id}/revoke` | token | Revoke a source and propagate quarantine |
| POST | `/derive` | token | Create a derived/redacted artifact |
| GET | `/lineage/{id}` | — | Lineage graph + edge metadata + attestation |
| GET | `/audit` | — | Audit event log (most recent first) |
| GET | `/metrics/permission-latency` | — | Latency statistics across audit events |

### Example (curl)

```bash
# Seed and capture a token
curl -s -X POST localhost:8000/seed | jq -r '.tokens.u_ceo'   # → <CEO_TOKEN>

# Read as CEO (allowed)
curl -s localhost:8000/artifacts/phase2_readiness_memo \
  -H "Authorization: Bearer <CEO_TOKEN>" | jq '.access'
```

### Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

The suite (`backend/tests/test_biovault.py`) is the evidence for the compliance matrix below.

---

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and calls the backend at `http://localhost:8000`.
Override with `VITE_API_URL` environment variable.

---

## Demo Flow

The UI has a numbered step guide. The acting principal switcher selects that user's **capability
token** (not an arbitrary user id). Click each step in order, or run them manually:

| Step | Action | Expected result |
|---|---|---|
| 1 | Seed data | Tables reset; 6 users + tokens, 8 artifacts, capability grants loaded |
| 2 | CEO reads Phase II Readiness Memo | **ALLOW** — CEO holds read capability; sources active |
| 3 | CRO reads Phase II Readiness Memo | **DENY** — `missing_capability_grant` |
| 4 | Regulatory Lead reads Phase II Readiness Memo | **ALLOW** — has grant; sources active |
| 5 | CEO derives Redacted Phase II Memo | Created with attestation; adverse-event content excluded |
| 6 | CEO revokes Adverse Event Memo | `adverse_event_memo` → revoked; `phase2_readiness_memo` → quarantined |
| 7 | Regulatory Lead reads Phase II Readiness Memo | **DENY** — `derived_from_revoked_source` |
| 8 | CEO retries Redacted derive | **DENY** — `cannot_redact_revoked_source` (redaction is not a bypass) |

The audit log and permission latency panel update after every step.

---

## BasedAI Compliance Matrix

| Requirement | Implementation | Test / Evidence |
|---|---|---|
| Artifact-level, capability-based access (not role-based RAG) | `evaluate_access()` checks per-`(user, artifact, operation)` grants | `test_allow_deny_matrix` |
| Identity not caller-controlled | `resolve_principal()` resolves a hashed bearer token; `user_id` param ignored | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` |
| Secrets stored safely | Only SHA-256 token hashes persisted; plaintext returned once at seed | `seed()` returns `tokens`; `users.token_hash` column |
| Delegation requires authority | `grant_artifact` requires issuer `grant` capability; full provenance logged | `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` |
| Governed redaction (no bypass) | `redact` capability required on every parent; revoked sources rejected | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source` |
| Redaction attestation + lineage metadata | `redaction_attestations` table; `lineage_edges.inclusion/source_hash` | `test_governed_redaction_succeeds_on_healthy_sources` |
| Source revocation propagation (multi-level) | `revoke_artifact` BFS over `get_transitive_children` | `test_multi_level_revocation_propagation` |
| Audit every access attempt | `log_audit()` on read/derive/revoke/grant with `request_id` + `detail` | `test_audit_records_all_operation_types` |
| Deterministic, no LLM in permission path | Pure SQL/Python in `evaluate_access()` | code review; no model imports |
| Permission latency P99 < 200ms | Indexed lookups; `GET /metrics/permission-latency` | `test_permission_latency_p99_under_200ms` |
| Performance indexes | grant lookup, lineage parent/child, audit timestamp, token | `init_db()` `CREATE INDEX` statements |

---

## Seed Data

### Users

| ID | Name | Role | Team |
|---|---|---|---|
| `u_ceo` | Avery Chen | CEO | Leadership |
| `u_research` | Maya Patel | Research Scientist | R&D |
| `u_compchem` | Leo Morgan | Computational Chemist | R&D |
| `u_regulatory` | Nora Singh | Regulatory Lead | Regulatory |
| `u_cro` | Owen Brooks | External CRO Scientist | Partner |
| `u_intern` | Iris Lopez | Intern | R&D |

### Artifacts

| ID | Title | Type | Sensitivity |
|---|---|---|---|
| `public_target_paper` | Open Target Biology Paper | source | public |
| `internal_sar_table` | Internal SAR Table | source | restricted |
| `docking_report` | Docking Report | source | internal |
| `toxicity_report` | GLP Toxicity Report | source | restricted |
| `cro_assay_report` | CRO Assay Report | source | internal |
| `adverse_event_memo` | Adverse Event Memo | source | confidential |
| `board_update` | Board Update | source | confidential |
| `phase2_readiness_memo` | Phase II Readiness Memo | derived | confidential |

### Initial Capability Grants

| User | Capabilities |
|---|---|
| CEO | All artifacts: `read`, `derive`, `revoke`, `grant`, `redact` |
| Regulatory Lead | `read` on toxicity_report, adverse_event_memo, phase2_readiness_memo |
| Research Scientist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report, toxicity_report |
| Computational Chemist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report |
| External CRO Scientist | `read` on public_target_paper, cro_assay_report |
| Intern | `read` on public_target_paper |

### Lineage

`phase2_readiness_memo` is derived from:
- `public_target_paper`
- `internal_sar_table`
- `toxicity_report`
- `adverse_event_memo`
