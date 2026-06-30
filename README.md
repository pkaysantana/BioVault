# BioVault

**Capability-secured artifact memory for AI science agents — deterministic, lineage-aware, LLM-free in the permission path.**

Built for the **BasedAI Enterprise Memory Governance at Scale** track. BioVault shows how a multi-user AI workspace prevents agent-created artifacts from leaking sensitive source data, even after the source is revoked at runtime.

> **Classification:** Educational prototype / hackathon MVP. Not validated scientific logic, clinical decision support, or a regulated medical device.

---

## One-line pitch

> BioVault enforces artifact-level capability checks — not role-level policies — so a derived clinical memo can be quarantined the moment its source data is revoked, without touching a model.

---

## Problem statement

In an AI-assisted biotech workspace multiple agents write, summarise, and derive artifacts from sensitive source data (SAR tables, toxicity reports, adverse-event memos). Standard RBAC gives users permission to a *resource type* (e.g. "internal documents"). It cannot answer: *"Should this particular derived memo still be readable now that the adverse-event source it was built from has been revoked?"*

BioVault answers that question deterministically, in <200 ms, without asking any model.

---

## Why this is not RBAC

| Dimension | RBAC | BioVault |
|---|---|---|
| Grant unit | User → Role → Resource type | User → Capability → **Exact artifact** |
| Derived artifact access | Inherits role from creator | Checked independently against every source |
| Revocation granularity | Disable user or role | Revoke **one source artifact**; propagate to all downstream derived artifacts |
| Permission computation | Policy table lookup | `evaluate_access()` — deterministic SQL/Python, no model |
| Identity binding | Username/session cookie | SHA-256 hashed **capability token**; `?user_id=` carries zero authority |
| Audit | Optional middleware | Every read/derive/revoke/grant writes a structured audit event |

---

## Architecture

```
Browser (React/Vite  :5173)
        │
        │  Authorization: Bearer <capability_token>
        │  (?user_id= query params are ignored — zero authority)
        ▼
FastAPI  (:8000)
        │
        ├─ resolve_principal()      hash token → principal_id
        │                           (unknown token → 401)
        │
        ├─ evaluate_access()        deterministic SQL/Python, no LLM
        │   ├─ artifact exists and is active/redacted?
        │   ├─ user holds non-revoked capability grant for operation?
        │   └─ for derived artifacts: all source artifacts accessible?
        │       (redacted edges: check only `included` parents)
        │
        ├─ action (read/derive/revoke/grant)
        │
        ├─ log_audit()              request_id, principal, artifact, operation,
        │                           decision, reason, latency_ms, detail JSON
        │
        │  ── only after authorisation ──────────────────────────────────────
        │  (optional) open-weight model reads the authorised content
        │  Qwen / Llama / Mistral / GLM / BGE / E5 / Nomic
        └─────────────────────────────────────────────────────────────────────
        │
        ▼
SQLite  biovault.db
        ├─ users                    id, name, role, team, token_hash
        ├─ artifacts                id, title, type, sensitivity, status,
        │                           encrypted_content, created_by
        ├─ capability_grants        user_id, artifact_id, operation, revoked, expires_at
        ├─ lineage_edges            parent_id, child_id, inclusion, source_hash, reason
        ├─ audit_events             timestamp, user_id, artifact_id, operation,
        │                           decision, reason, latency_ms, request_id, detail
        └─ redaction_attestations   artifact_id, created_by, reason, source_hashes
```

Indexes on `(user_id, artifact_id, operation)`, lineage parent/child, audit timestamp, and token hash keep P99 well under 200 ms on commodity hardware.

---

## BasedAI Compliance Matrix

| BasedAI Requirement | BioVault Implementation | Test / Evidence |
|---|---|---|
| Artifact-level access, not role-based | `evaluate_access()` checks per-`(principal, artifact, operation)` capability grants | `test_allow_deny_matrix` |
| Capability-bound identity — no spoofing | `resolve_principal()` hashes bearer token; `?user_id=` ignored | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` |
| Secrets stored safely | Only SHA-256 token hashes persisted; plaintext returned once from `POST /seed` | `seed()` returns `tokens`; `users.token_hash` column |
| Grant delegation requires issuer authority | `POST /artifacts/{id}/grant` requires issuer `grant` capability; logs `grant_id`, `issuer`, `subject`, `scope`, `purpose`, `request_id` | `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` |
| Governed redaction — no bypass | `redact` capability required on every parent; redaction from revoked source denied at API layer | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source` |
| Lineage metadata and attestation | `lineage_edges` stores `source_hash`, `inclusion`, `dependency_type`, `reason`; `redaction_attestations` table | `test_governed_redaction_succeeds_on_healthy_sources` |
| Source revocation propagates | `revoke_artifact` BFS-quarantines all active derived descendants; audit event per artifact | `test_multi_level_revocation_propagation` |
| Every access attempt audited | `log_audit()` on read / derive / revoke / grant; `request_id` + structured `detail` | `test_audit_records_all_operation_types` |
| No LLM in permission path | Pure SQL + Python in `evaluate_access()`; zero model imports | `grep -r "openai\|anthropic\|llm" backend/` → 0 matches |
| P99 permission check < 200 ms | Indexed lookups; `GET /metrics/permission-latency` exposes live p99 | `test_permission_latency_p99_under_200ms` (200 samples) |

---

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runs at `http://localhost:8000`. Interactive docs at `/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`. Override backend URL with `VITE_API_URL`.

### Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Expected output: **11 passed** (includes P99 latency benchmark).

---

## Endpoints

All artifact operations require `Authorization: Bearer <token>`. A `?user_id=` param is ignored for authority.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| POST | `/seed` | — | Reset; returns plaintext principal tokens once |
| GET | `/users` | — | List users (no tokens) |
| GET | `/artifacts` | — | List artifacts (no content) |
| GET | `/artifacts/{id}` | token | Read artifact — permission check + audit |
| POST | `/artifacts/{id}/grant` | token | Grant capability (issuer needs `grant` authority) |
| POST | `/artifacts/{id}/revoke` | token | Revoke source + propagate quarantine |
| POST | `/derive` | token | Derive or redact an artifact |
| POST | `/query` | token | Agent integration stub — enforces auth before returning content |
| GET | `/lineage/{id}` | — | Lineage graph + edge metadata + attestation |
| GET | `/audit` | — | Audit log, most recent first |
| GET | `/metrics/permission-latency` | — | Live P99 / mean / p95 over audit events |

---

## Demo Script (6 steps)

Open the frontend at `http://localhost:5173`. Click **Seed Demo**, then work through the Demo Flow panel:

| Step | Action | Expected result |
|---|---|---|
| 1 | CEO opens Phase II Readiness Memo | **ALLOW** — `capability_and_lineage_valid`; content decrypted and shown |
| 2 | External CRO attempts Phase II Readiness Memo | **DENY** — `missing_capability_grant`; content withheld |
| 3 | Regulatory Lead opens Phase II Readiness Memo | **ALLOW** — has `read` grant; all sources healthy |
| 4 | Revoke Adverse Event Memo | Derives "Exec Brief" from Phase II, then revokes source; quarantine cascades to both derived artifacts |
| 5 | Inspect quarantined state | **DENY** — `derived_from_revoked_source`; artifact list shows amber `quarantined` badges on Phase II memo and Exec Brief |
| 6 | Audit log & latency evidence | Compliance matrix shows live P99; audit log shows every decision with reason, principal, and `request_id` |

See `docs/DEMO_SCRIPT.md` for full 2-minute and 30-second scripts.

---

## Seed Data

### Users and capability grants

| ID | Name | Role | Initial capabilities |
|---|---|---|---|
| `u_ceo` | Avery Chen | CEO | `read`, `derive`, `revoke`, `grant`, `redact` on all artifacts |
| `u_regulatory` | Nora Singh | Regulatory Lead | `read` on toxicity_report, adverse_event_memo, phase2_readiness_memo |
| `u_research` | Maya Patel | Research Scientist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report, toxicity_report |
| `u_compchem` | Leo Morgan | Computational Chemist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report |
| `u_cro` | Owen Brooks | External CRO Scientist | `read` on public_target_paper, cro_assay_report |
| `u_intern` | Iris Lopez | Intern | `read` on public_target_paper only |

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

### Lineage

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo ──► (Exec Brief, derived in step 4)
toxicity_report     ──┤
adverse_event_memo  ──┘
```

Revoking `adverse_event_memo` quarantines `phase2_readiness_memo` and any artifacts derived from it.

---

## Security model

### Trust boundary

The API surface is the trust boundary. Every mutation endpoint resolves a principal from a hashed bearer token before any other logic runs. No principal = 401.

### Permission logic

`evaluate_access(principal_id, artifact_id, operation)`:

1. Artifact must exist and be `active` or `redacted`.
2. Principal must hold a non-revoked, non-expired `capability_grant` for `(artifact_id, operation)`.
3. If the artifact is derived, every parent that was **included** (not redacted away) must also pass `evaluate_access` for the same principal and `read` operation recursively.

Steps run in pure Python/SQL. No probabilistic model is consulted. The decision is deterministic.

### Governed redaction

A derived artifact may omit sensitive parent content by setting `redacted=true` on a `POST /derive` call. This is **not** a bypass:

- The issuer must hold a `redact` capability on every parent they omit.
- Redaction from a `revoked` or `quarantined` source is denied.
- A `redaction_attestation` row is written naming the artifact, reason, source hashes, and issuer.

Redacted edges are excluded from the transitive source check, so a redacted summary's access does not depend on the excluded parent remaining healthy.

### Revocation

`POST /artifacts/{id}/revoke` marks the target artifact `revoked`, then BFS-traverses the lineage graph, marking every reachable `active` or `redacted` descendant `quarantined`. An audit event is written for each artifact affected. Future reads of quarantined artifacts return `derived_from_revoked_source`.

---

## Residual limitations

| Limitation | Notes |
|---|---|
| Fernet key is hard-coded | Demo only; in production, rotate via a KMS |
| SQLite concurrency | Single writer; replace with PostgreSQL for multi-process deployments |
| No token expiry enforcement at verify time | `expires_at` column exists and is persisted; runtime expiry check is a one-line addition |
| No refresh tokens | Tokens are single-use demo secrets; production would use short-lived JWTs + refresh flow |
| BFS quarantine is synchronous | For large lineage graphs, push to a background queue (Celery/ARQ) |
| No row-level encryption key per artifact | Single Fernet key; per-artifact keys + KMS is the production path |
| Tests use SQLite in-process | Cross-process isolation requires a test-scoped temp DB with proper teardown |

---

## Open-weight runtime compatibility

BioVault's permission layer makes **zero model calls**. It is fully compatible with any open-weight model a BasedAI agent runtime chooses to use:

- Qwen, Llama, Mistral, GLM, BGE, E5, Nomic — any model may receive artifact content *after* authorisation.
- The `POST /query` endpoint is a lightweight adapter stub demonstrating this pattern: BioVault enforces the permission gate, then returns the authorised content blob for the caller's model to process.
- No closed-model runtime dependency is introduced. The permission boundary is enforced **before** any model output touches an artifact, not inside the model.

See `docs/ARCHITECTURE.md` for the full request flow.
