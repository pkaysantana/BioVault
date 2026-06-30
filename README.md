# BioVault

**Prevent AI agents from leaking company memory — like payroll — into marketing answers.**

Deterministic, lineage-aware, LLM-free capability enforcement for shared artifact memory.

Built for the **BasedAI Enterprise Memory Governance at Scale** track.

> **Classification:** Educational prototype / hackathon MVP. Not validated scientific logic, clinical decision support, or a regulated medical device.

---

## One-line pitch

> BioVault enforces artifact-level capability checks so a marketing AI agent asking for "Q3 cost data" is denied the payroll-mixed margin report — and revoking the payroll source automatically quarantines every derived artifact that included it, without touching a model.

---

## The problem (BasedAI workshop use case)

AI agents in company memory systems — Notion, Confluence, internal wikis — create derived artifacts: margin reports, cost summaries, staffing analyses — built from sensitive source documents: payroll registers, vendor contracts, compensation tables.

Standard access control answers the question "can this user read files?" BioVault answers a harder question: **"can this agent surface this derived artifact when one of its source documents contains payroll data that Marketing should never see?"**

Existing approaches fail here:

| Failure mode | Why it fails |
|---|---|
| **Duplicate files into team silos** | Marketing gets a copy of shared files. Changes don't sync. A payroll file copied into a "shared" folder becomes invisible to governance. You cannot revoke a copy you don't track. Silo drift makes revocation unenforceable. |
| **LLM-based sensitivity filtering** | Route every retrieval through a model to classify sensitivity. Token-heavy, latency compounds, models can be confused or prompted into surfacing revoked context. Not a security boundary. |
| **Role-based access control (RBAC)** | Grants access by role ("Marketing can read internal files"). No concept of artifact lineage. Revoking a source does not automatically close access to derived outputs. |

BioVault addresses this with a capability-per-artifact model, transitive lineage tracking, and propagating revocation — all enforced before any model sees any content. **Zero model tokens in the permission path.**

---

## Default demo: SME / company-memory payroll leakage

The default seed scenario:

- **One global company memory store** — no team silos, no copies
- **Marketing** has read access to campaign costs and vendor contracts
- **Marketing does NOT** have access to the Q3 Growth Margin Report — a governed derived artifact synthesised from campaign costs, vendor contracts, and **payroll data**
- **Finance** can read the Q3 report (they have a capability grant and access to payroll)
- **Owner revokes Payroll Salary Register** → Q3 Growth Margin Report is automatically quarantined through lineage
- **Finance is now denied** the Q3 report — `derived_from_revoked_source`
- Every decision is audited with `request_id`, `principal`, `decision`, `reason`, and `latency_ms`

The key claim: Marketing lacks a capability grant on the payroll-mixed derived artifact, and payroll revocation propagates to that derived artifact through lineage — deterministically, sub-millisecond, with zero model tokens consumed.

### SME principals

| ID | Name | Role | Capabilities |
|---|---|---|---|
| `u_owner` | Alex Kim | Owner | `read`, `derive`, `revoke`, `grant`, `redact` on all artifacts |
| `u_finance` | Jordan Lee | Finance Lead | `read` on payroll register, Q3 report, handbook |
| `u_marketing` | Morgan Chen | Marketing Manager | `read` on campaign costs, vendor contracts, customer feedback, handbook |
| `u_hr` | Riley Park | HR Lead | `read` on payroll register, handbook |
| `u_ops` | Sam Rivera | Operations Manager | `read` on vendor contracts, handbook |
| `u_contractor` | Casey Jones | External Contractor | `read` on handbook only |

### SME artifacts and lineage

```
campaign_cost_summary   ──┐
vendor_contracts        ──┼──► q3_growth_margin_report  (confidential, derived)
payroll_salary_register ──┘

Revoking payroll_salary_register quarantines q3_growth_margin_report.
```

### Seeding

```
POST /seed?scenario=sme       # default
POST /seed?scenario=biotech   # AI-science pharma R&D (secondary scenario)
```

---

## Secondary demo: AI science / biotech

The biotech scenario is preserved as a secondary demo. Switch to it using the **scenario switcher** in the UI, or seed it with `POST /seed?scenario=biotech`.

This scenario models a pharmaceutical R&D kinase drug program. An AI science agent derives a Phase II readiness memo from four source documents. When the adverse-event memo is revoked for data integrity reasons, the derived memo and all its children are automatically quarantined — using the same permission engine and lineage propagation as the SME scenario.

---

## Why this is not RBAC

| RBAC | BioVault |
|---|---|
| Grants access by role (e.g. "Marketing can read internal files") | Grants access by explicit capability on each artifact |
| Revoking a role affects the user, not the artifacts | Revoking a source artifact propagates quarantine to all derived descendants |
| No concept of artifact lineage | Every derived artifact tracks which source artifacts it was built from |
| Access to a derived document is independent of its sources | Access to a derived document requires all included sources to be in an active state |
| Adding a user to a group grants broad access | Granting a capability is narrow: `(user, artifact, operation)` with optional expiry |

Marketing can read `campaign_cost_summary` not because of their role, but because they hold a `read` capability grant on that specific artifact. They cannot read `q3_growth_margin_report` not because of their role, but because they lack a capability grant on it — and even if they had one, revoking `payroll_salary_register` would quarantine the Q3 report through lineage.

---

## Architecture

```
Agent / model runtime (any open-weight model)
        │
        │  POST /query  { artifact_id, purpose }
        │  Authorization: Bearer <capability_token>
        │
        ▼
FastAPI  (:8000)
        │
        ├─ resolve_principal()    SHA-256(token) → principal_id
        │                         ?user_id= query param has zero authority
        ├─ evaluate_access()      deterministic SQL/Python  ← 0 model tokens
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
| Artifact-level access, not role-based | `evaluate_access()` checks per-`(principal, artifact, operation)` capability grants | `test_allow_deny_matrix` + `test_sme_marketing_cannot_read_payroll_mixed_report` |
| Capability-bound identity — no spoofing | `resolve_principal()` hashes bearer token; `?user_id=` param ignored | `test_user_id_query_param_is_not_authority`, `test_missing_and_invalid_token_denied` |
| Secrets stored safely | Only SHA-256 token hashes persisted; plaintext returned once at seed time | `POST /seed` response; `users.token_hash` column |
| Grant delegation requires authority | `POST /artifacts/{id}/grant` requires issuer `grant` capability | `test_unauthorised_grant_denied`, `test_authorised_grant_succeeds` |
| Governed redaction — no bypass | `redact` capability required on every parent; redaction from a revoked source denied | `test_redaction_requires_redact_authority`, `test_redaction_cannot_launder_revoked_source` |
| Lineage metadata and attestation | `lineage_edges` stores `source_hash`, `inclusion`, `dependency_type`, `reason` | `test_governed_redaction_succeeds_on_healthy_sources` |
| Source revocation propagates | BFS-quarantines all active derived descendants; audit event per quarantined artifact | `test_multi_level_revocation_propagation` + `test_sme_payroll_revocation_quarantines_derived_report` |
| Every access attempt audited | `log_audit()` on every decision with `request_id` + structured `detail` | `test_audit_records_all_operation_types` + `test_sme_audit_records_request_id_purpose_principal_operation_artifact` |
| No LLM in permission path | Pure SQL + Python in `evaluate_access()`; `grep -r "openai\|anthropic\|langchain" backend/app/` returns nothing | Code review; zero model imports |
| P99 permission check < 200 ms | Indexed lookups; `GET /metrics/permission-latency` exposes live p99 | `test_permission_latency_p99_under_200ms` (200 samples, asserts < 200 ms) |

---

## Security model

**What BioVault enforces:**

1. *Identity is the token.* `resolve_principal()` is a FastAPI dependency on every protected route. It hashes the bearer token, looks up the principal, and returns a `principal_id`. No other input (query string, request body, cookie) can assert identity.

2. *Every operation is capability-gated.* `has_grant(conn, user_id, artifact_id, operation)` checks for a non-revoked, non-expired row in `capability_grants`. There is no wildcard grant and no privilege escalation path.

3. *Lineage integrity check.* For derived artifacts, `evaluate_access` additionally checks that no included source is `revoked` or `quarantined`. This runs on every read, not just at derivation time.

4. *Governed redaction.* Creating a `redacted` artifact requires the `redact` capability on every parent. Deriving from a revoked source is denied regardless of authority.

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

### Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
# expected: 20 passed
# 13 biotech/core tests + 7 SME scenario tests
```

---

## API reference

All protected routes require `Authorization: Bearer <token>`. A `?user_id=` param has no authority.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| POST | `/seed?scenario=sme` | — | Reset; default SME scenario; returns plaintext tokens once |
| POST | `/seed?scenario=biotech` | — | Reset; biotech/pharma scenario |
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

See `docs/DEMO_SCRIPT.md` for the 2-minute judge demo (SME scenario) and the biotech secondary scenario.

**Quick reference — SME scenario, 8 steps:**

| Step | Who | Action | Expected |
|---|---|---|---|
| 1 | Marketing (Morgan Chen) | Open Campaign Cost Summary | **ALLOW** — content decrypted and shown |
| 2 | Marketing (Morgan Chen) | Open Q3 Growth Margin Report | **DENY** — missing_capability_grant; no content |
| 3 | Finance (Jordan Lee) | Open Q3 Growth Margin Report | **ALLOW** — sources healthy |
| 4 | — | Inspect lineage of Q3 report | campaign_cost_summary + vendor_contracts + payroll_salary_register |
| 5 | Owner (Alex Kim) | Revoke Payroll Salary Register | Quarantine propagates to Q3 Growth Margin Report |
| 6 | — | Show quarantine state | Q3 report shows amber `quarantined` badge |
| 7 | Finance (Jordan Lee) | Open Q3 Growth Margin Report | **DENY** — derived_from_revoked_source |
| 8 | — | Review audit log + compliance matrix | Every decision logged; P99 shown live |
