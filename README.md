# BioVault

**Capability-secured artifact memory for AI science agents — deterministic, lineage-aware, LLM-free in the permission path.**

Built for the **BasedAI Enterprise Memory Governance at Scale** track. BioVault shows how a multi-user AI workspace prevents agent-created artifacts from leaking sensitive source data, even after the source is revoked at runtime.

> **Classification:** Educational prototype / hackathon MVP. Not validated scientific logic, clinical decision support, or a regulated medical device.

---

## One-line pitch

> BioVault enforces artifact-level capability checks — not role-level policies — so a derived clinical memo can be quarantined the moment its source data is revoked, without touching a model.

---

## Architecture

```
Browser (React/Vite  :5173)
        │
        │  Authorization: Bearer <capability_token>
        │  (user_id query params are ignored — they carry zero authority)
        ▼
FastAPI  (:8000)
        │
        ├─ resolve_principal()      hash token → principal_id
        ├─ evaluate_access()        deterministic SQL/Python, no LLM
        └─ log_audit()              request_id, operation, decision, latency_ms
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

Indexes on grant lookup `(user_id, artifact_id, operation)`, lineage parent/child, audit timestamp, and token hash keep P99 well under 200 ms on commodity hardware.

---

## BasedAI Compliance Matrix

| BasedAI Requirement | BioVault Implementation | Test / Evidence |
|---|---|---|
| Artifact-level access, not role-based | `evaluate_access()` checks per-`(principal, artifact, operation)` capability grants | `test_allow_deny_matrix` |
| Capability-bound identity — no spoofing | `resolve_principal()` hashes bearer token and resolves principal; `?user_id=` param ignored | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` |
| Secrets stored safely | Only SHA-256 token hashes persisted; plaintext returned once from `POST /seed` | `seed()` returns `tokens`; `users.token_hash` column |
| Grant delegation requires authority | `POST /artifacts/{id}/grant` requires issuer `grant` capability; logs `grant_id`, `issuer`, `subject`, `scope`, `purpose`, `request_id` | `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` |
| Governed redaction — no bypass | `redact` capability required on every parent; redaction from revoked source denied | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source` |
| Lineage metadata and attestation | `lineage_edges` stores `source_hash`, `inclusion`, `dependency_type`, `reason`; `redaction_attestations` table | `test_governed_redaction_succeeds_on_healthy_sources` |
| Source revocation propagates | `revoke_artifact` BFS-quarantines all active derived descendants; audit events written per artifact | `test_multi_level_revocation_propagation` |
| Every access attempt audited | `log_audit()` on read / derive / revoke / grant; `request_id` + structured `detail` | `test_audit_records_all_operation_types` |
| No LLM in permission path | Pure SQL + Python in `evaluate_access()`; zero model imports | code review; `grep -r "openai\|anthropic\|llm" backend/` returns nothing |
| P99 permission check &lt; 200 ms | Indexed lookups; `GET /metrics/permission-latency` exposes live p99 | `test_permission_latency_p99_under_200ms` (200 samples, asserts &lt; 200 ms) |

**Model compatibility note:** BioVault's permission layer is model-agnostic and makes no model calls. It is compatible with any open-weight model a BasedAI agent runtime chooses to use. The permission boundary is enforced before any model output reaches an artifact, not inside the model.

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

Expected output: **11 passed** (includes latency P99 benchmark).

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
| GET | `/lineage/{id}` | — | Lineage graph + edge metadata + attestation |
| GET | `/audit` | — | Audit log, most recent first |
| GET | `/metrics/permission-latency` | — | Live P99 / mean / p95 over audit events |

---

## Demo Script (5 steps)

Open the frontend at `http://localhost:5173`. Click steps in the Demo Flow panel:

| Step | Action | What to show the judge |
|---|---|---|
| 1 | CEO opens Phase II Readiness Memo | **ALLOW** — capability_and_lineage_valid; content decrypted and shown |
| 2 | CRO opens Phase II Readiness Memo | **DENY** — missing_capability_grant; content withheld |
| 3 | Revoke Adverse Event Memo | Derives "Exec Brief" from Phase II, then revokes source; quarantine cascades to both derived artifacts |
| 4 | Inspect quarantined state | **DENY** — derived_from_revoked_source; artifact list shows amber quarantined badges on Phase II memo and Exec Brief |
| 5 | Audit log &amp; latency evidence | Compliance matrix shows live P99; audit log shows every decision with reason, principal, and request_id |

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
| `phase2_readiness_memo` | Phase II Readiness Memo | derived (from public paper + SAR + toxicity + adverse event) | confidential |

### Lineage

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo
toxicity_report     ──┤
adverse_event_memo  ──┘
```

Revoking `adverse_event_memo` quarantines `phase2_readiness_memo` and any artifacts derived from it.
