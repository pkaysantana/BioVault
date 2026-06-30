# BioVault

**Capability-secured artifact memory for AI science agents — deterministic, lineage-aware, LLM-free in the permission path.**

Built for the **BasedAI Enterprise Memory Governance at Scale** track.

> **Classification:** Educational prototype / hackathon MVP. Not validated scientific logic, clinical decision support, or a regulated medical device.

---

## One-line pitch

> BioVault enforces artifact-level capability checks — not role-level policies — so a derived clinical memo is quarantined the moment its source data is revoked, without touching a model.

---

## Problem statement

AI science agents in biotech R&D create derived artifacts — summaries, readiness memos, board updates — that are built from sensitive source data: SAR tables, toxicity reports, adverse-event memos. Standard access control answers the question "can this user read files?" BioVault answers a harder question: **"can this agent surface this derived artifact when one of its source documents has just been revoked?"**

Existing approaches fail here:
- RBAC grants access by role, not by artifact. Revoking a source does not automatically close access to derived outputs.
- RAG pipelines decide what to retrieve using a model, not a deterministic rule. A model can be prompted or confused into surfacing revoked context.
- Per-document ACLs do not track lineage, so derived artifacts are not automatically affected when a source changes state.

BioVault addresses this with a capability-per-artifact model, transitive lineage tracking, and propagating revocation — all enforced before any model sees any content.

---

## Why this is not RBAC

| RBAC | BioVault |
|---|---|
| Grants access by role (e.g. "Regulatory Lead can read restricted files") | Grants access by explicit capability on each artifact |
| Revoking a role affects the user, not the artifacts | Revoking a source artifact propagates quarantine to all derived descendants |
| No concept of artifact lineage | Every derived artifact tracks which source artifacts it was built from |
| Access to a derived document is independent of its sources | Access to a derived document requires all included sources to be in an active state |
| Adding a user to a group grants broad access | Granting a capability is narrow: `(user, artifact, operation)` with optional expiry |

A Regulatory Lead can read `phase2_readiness_memo` not because of their role, but because they hold a `read` capability grant on that specific artifact and all its included source artifacts are `active`. The moment `adverse_event_memo` is revoked, the Phase II memo is automatically quarantined and every read attempt is denied — regardless of role.

---

## Architecture

```
Open-weight model (Qwen / Llama / Mistral / GLM / any)
        │
        │  POST /query  { artifact_id, purpose }
        │  Authorization: Bearer <capability_token>
        │
        ▼
FastAPI  (:8000)
        │
        ├─ resolve_principal()    SHA-256(token) → principal_id
        │                         ?user_id= query param has zero authority
        ├─ evaluate_access()      deterministic SQL/Python
        │   ├─ user exists?
        │   ├─ artifact exists and is active/redacted?
        │   ├─ principal holds non-revoked capability grant?
        │   └─ all included source artifacts active? (lineage integrity)
        ├─ log_audit()            timestamp, principal, artifact, op,
        │                         decision, reason, latency_ms, request_id
        └─ decrypt + return       only if decision == allow
        │
        ▼
SQLite  biovault.db
  users                  id, name, role, team, token_hash (SHA-256 only)
  artifacts              id, title, type, sensitivity, status, encrypted_content
  capability_grants      user_id × artifact_id × operation, revoked, expires_at
  lineage_edges          parent_id, child_id, inclusion, source_hash, reason
  audit_events           timestamp, user_id, artifact_id, op, decision,
                         reason, latency_ms, request_id, detail (JSON)
  redaction_attestations artifact_id, created_by, reason, source_hashes

Indexes:  grant lookup (user_id, artifact_id, operation)
          lineage parent / child
          audit timestamp
          token hash
```

---

## BasedAI Compliance Matrix

| BasedAI Requirement | BioVault Implementation | Test / Evidence |
|---|---|---|
| Artifact-level access, not role-based | `evaluate_access()` checks per-`(principal, artifact, operation)` capability grants | `test_allow_deny_matrix` |
| Capability-bound identity — no spoofing | `resolve_principal()` hashes bearer token; `?user_id=` param ignored | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` |
| Secrets stored safely | Only SHA-256 token hashes persisted; plaintext returned once at seed time | `POST /seed` response; `users.token_hash` column |
| Grant delegation requires authority | `POST /artifacts/{id}/grant` requires issuer `grant` capability; logs `grant_id`, `issuer`, `subject`, `scope`, `purpose`, `request_id` | `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` |
| Governed redaction — no bypass | `redact` capability required on every parent; redaction from a revoked source denied with `cannot_redact_revoked_source` | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source` |
| Lineage metadata and attestation | `lineage_edges` stores `source_hash`, `inclusion`, `dependency_type`, `reason`; `redaction_attestations` table records who/when/why | `test_governed_redaction_succeeds_on_healthy_sources` |
| Source revocation propagates | `revoke_artifact` BFS-quarantines all active derived descendants; audit event written per quarantined artifact | `test_multi_level_revocation_propagation` |
| Every access attempt audited | `log_audit()` on read / derive / revoke / grant / redact with `request_id` + structured `detail` | `test_audit_records_all_operation_types` |
| No LLM in permission path | Pure SQL + Python in `evaluate_access()`; `grep -r "openai\|anthropic\|langchain" backend/app/` returns nothing | Code review; zero model imports |
| P99 permission check &lt; 200 ms | Indexed lookups; `GET /metrics/permission-latency` exposes live p99 | `test_permission_latency_p99_under_200ms` (200 samples, asserts &lt; 200 ms) |

---

## Security model

**What BioVault enforces:**

1. *Identity is the token.* `resolve_principal()` is a FastAPI dependency on every protected route. It hashes the bearer token, looks up the principal, and returns a `principal_id`. No other input (query string, request body, cookie) can assert identity.

2. *Every operation is capability-gated.* `has_grant(conn, user_id, artifact_id, operation)` checks for a non-revoked, non-expired row in `capability_grants`. There is no wildcard grant and no privilege escalation path.

3. *Lineage integrity check.* For derived artifacts, `evaluate_access` additionally checks that no included source is `revoked` or `quarantined`. This runs on every read, not just at derivation time.

4. *Governed redaction.* Creating a `redacted` artifact requires the `redact` capability on every parent. Deriving from a revoked source is denied regardless of authority. A redaction attestation records the source hashes, included/excluded parents, reason, and request ID.

5. *Audit is unconditional.* `log_audit()` is called for every decision including denials, propagated quarantines, and failed grant attempts.

**What BioVault does not enforce (demo-only limitations):**

- The Fernet encryption key is deterministically derived from a hardcoded phrase. In production, use a secrets manager.
- `POST /seed` returns plaintext tokens in the response body. In production, deliver tokens out-of-band.
- SQLite is not suitable for multi-writer production use.
- Token revocation (logging out a principal) is not implemented.

---

## Open-weight model compatibility

BioVault makes **zero model calls** in its permission path. It is compatible with any open-weight runtime — Qwen, Llama 3, Mistral, Phi, GLM, BGE, E5, Nomic, or any model accessible via a tool-calling interface.

The integration pattern:

```
Agent loop:
  1. Agent decides which artifact to retrieve.
  2. Agent calls POST /query with its capability token.
  3. If decision == "allow": use plaintext_content as context for generation.
  4. If decision == "deny": inform the user; do not generate from that artifact.
  5. Log all decisions for audit.
```

The model is outside the permission boundary. It never decides whether access is granted. See `docs/ARCHITECTURE.md` for the full request flow and `docs/DEMO_SCRIPT.md` for the live demo.

---

## Residual limitations

| Limitation | Impact | Path to production |
|---|---|---|
| Hardcoded Fernet key | Decryptable by anyone with the source code | Replace with KMS (AWS, GCP, HashiCorp Vault) |
| SQLite single-writer | Unusable under concurrent agent load | Replace with PostgreSQL + connection pool |
| Tokens never expire server-side | Leaked token persists until manual DB edit | Add `token_expires_at` + rotation endpoint |
| No token revocation | A compromised principal cannot be locked out without DB edit | Add `POST /principals/{id}/rotate-token` |
| Lineage is direct-edge only in revoke propagation | A chain of 3+ derivations is correctly handled by BFS but not stress-tested at scale | Add benchmark with 100-node lineage graph |
| `POST /seed` exposes plaintext tokens in HTTP response | Fine for demo; unacceptable in production | Deliver tokens via secure channel; remove from response |

---

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Runs at `http://localhost:8000`. Interactive docs at `/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`. Override backend URL with `VITE_API_BASE_URL` (see `frontend/.env.example`).

Deploying for judges? See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — **recommended:** unified Vercel deploy from repo root (`vercel.json`); **alternative:** Render backend + Vercel frontend.

### Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
# expected: 13 passed (includes P99 latency benchmark and audit evidence tests)
```

---

## API reference

All protected routes require `Authorization: Bearer <token>`. A `?user_id=` param has no authority.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| POST | `/seed` | — | Reset; returns plaintext tokens once for demo use |
| GET | `/users` | — | List users (no token hashes) |
| GET | `/artifacts` | — | List artifacts (no content) |
| GET | `/artifacts/{id}` | token | Read artifact — permission check + audit event |
| POST | `/artifacts/{id}/grant` | token | Grant capability (issuer needs `grant` authority) |
| POST | `/artifacts/{id}/revoke` | token | Revoke source + propagate quarantine to descendants |
| POST | `/query` | token | **Agent gate** — check + return content if allowed; deny with no content if not |
| POST | `/derive` | token | Derive or governed-redact an artifact |
| GET | `/lineage/{id}` | — | Lineage graph + edge metadata + redaction attestation |
| GET | `/audit` | — | Audit log, most recent first |
| GET | `/metrics/permission-latency` | — | Live p99 / p95 / mean over audit events |

---

## Demo script

See `docs/DEMO_SCRIPT.md` for the 2-minute judge demo and 30-second fallback.

**Quick reference — 6 steps, click in order in the UI:**

| Step | Who | Action | Expected |
|---|---|---|---|
| 1 | CEO (Avery Chen) | Open Phase II Readiness Memo | **ALLOW** — content decrypted and shown |
| 2 | External CRO (Owen Brooks) | Open Phase II Readiness Memo | **DENY** — missing_capability_grant |
| 3 | Regulatory Lead (Nora Singh) | Open Phase II Readiness Memo | **ALLOW** — sources healthy |
| 4 | CEO | Revoke Adverse Event Memo | Derives exec brief, then revokes; quarantine cascades to 2 artifacts |
| 5 | CEO | Open Phase II Readiness Memo | **DENY** — derived_from_revoked_source; amber badges on list |
| 6 | — | Review audit log + compliance matrix | Every decision logged; P99 shown live |

---

## Seed data

### Users

| ID | Name | Role | Capabilities |
|---|---|---|---|
| `u_ceo` | Avery Chen | CEO | `read`, `derive`, `revoke`, `grant`, `redact` on all artifacts |
| `u_regulatory` | Nora Singh | Regulatory Lead | `read` on toxicity_report, adverse_event_memo, phase2_readiness_memo |
| `u_research` | Maya Patel | Research Scientist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report, toxicity_report |
| `u_compchem` | Leo Morgan | Computational Chemist | `read`+`derive` on public_target_paper, internal_sar_table, docking_report |
| `u_cro` | Owen Brooks | External CRO Scientist | `read` on public_target_paper, cro_assay_report |
| `u_intern` | Iris Lopez | Intern | `read` on public_target_paper only |

### Artifacts and lineage

```
public_target_paper ──┐
internal_sar_table  ──┼──► phase2_readiness_memo ──► (exec brief — derived in demo)
toxicity_report     ──┤
adverse_event_memo  ──┘

Revoking adverse_event_memo quarantines phase2_readiness_memo and every
artifact derived from it.
```
