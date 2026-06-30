# BioVault — Architecture

---

## Request flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLIENT  (Browser / AI Agent / SDK caller)                          │
│                                                                     │
│  GET /artifacts/{id}                                                │
│  Authorization: Bearer bv_<plaintext_token>                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS / localhost
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI  (:8000)                                                   │
│                                                                     │
│  1. resolve_principal(token)                                        │
│     ├─ SHA-256(token) → lookup users.token_hash                     │
│     ├─ match found  → principal_id (e.g. "u_ceo")                   │
│     └─ no match     → 401 Unauthorized  ◄──── REQUEST ENDS HERE     │
│                                                                     │
│  2. evaluate_access(principal_id, artifact_id, operation)           │
│     ├─ artifact exists in DB?              no  → DENY artifact_not_found
│     ├─ artifact status is active/redacted? no  → DENY artifact_[status]
│     ├─ capability_grants row:                                       │
│     │    (principal_id, artifact_id, operation)                     │
│     │    non-revoked, non-expired?          no  → DENY missing_capability_grant
│     └─ if artifact is derived:                                      │
│          for each INCLUDED parent edge:                             │
│            evaluate_access(principal, parent, read)                 │
│            any DENY?                       yes → DENY derived_from_revoked_source
│     ► ALLOW   (decision is deterministic — same inputs → same output)
│                                                                     │
│  3. action                                                          │
│     ├─ read:   decrypt artifact content (Fernet)                    │
│     ├─ derive: write artifact + lineage_edges + redaction_attestation
│     ├─ revoke: mark revoked, BFS quarantine descendants             │
│     └─ grant:  verify issuer holds `grant` capability, write row    │
│                                                                     │
│  4. log_audit(request_id, principal, artifact, op, decision,        │
│               reason, latency_ms, detail_json)                      │
│                                                                     │
│  ── PERMISSION GATE CLOSED — authorised content only below ─────── │
│                                                                     │
│  5. (optional) open-weight model generation                         │
│     The authorised content blob may be forwarded to any             │
│     open-weight model the agent runtime chooses:                    │
│       Qwen  Llama  Mistral  GLM  BGE  E5  Nomic                     │
│     BioVault does not call any model itself.                        │
│     POST /query demonstrates this pattern as an adapter stub.       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SQLite  (biovault.db)                                              │
│                                                                     │
│  users                  id · name · role · team · token_hash        │
│  artifacts              id · title · type · sensitivity · status ·  │
│                         encrypted_content · created_by              │
│  capability_grants      user_id · artifact_id · operation ·         │
│                         revoked · expires_at                        │
│  lineage_edges          parent_id · child_id · inclusion ·          │
│                         source_hash · dependency_type · reason      │
│  audit_events           timestamp · user_id · artifact_id ·         │
│                         operation · decision · reason ·             │
│                         latency_ms · request_id · detail            │
│  redaction_attestations artifact_id · created_by · reason ·         │
│                         source_hashes                               │
│                                                                     │
│  Indexes                                                            │
│    idx_grants_lookup    (user_id, artifact_id, operation)           │
│    idx_lineage_parent   (parent_artifact_id)                        │
│    idx_lineage_child    (child_artifact_id)                         │
│    idx_audit_timestamp  (timestamp)                                 │
│    idx_users_token_hash (token_hash)                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key design decisions

### 1. Token-bound identity, not query-param identity

Early drafts accepted `?user_id=` for authority. This was replaced by `resolve_principal()`, which hashes the bearer token and looks up the matching user. The query param is still accepted for display convenience but carries zero authority. Spoofing a `user_id` query param produces the same result as omitting it.

### 2. Deterministic `evaluate_access()`

Permission checks call no model, no cache, no probabilistic component. The function is a pure recursive read over SQLite rows. Given identical inputs it always returns the same decision. This makes it auditable and testable (`test_allow_deny_matrix`, `test_multi_level_revocation_propagation`).

### 3. Governed redaction is not a bypass

`redacted=true` on `POST /derive` means the derived artifact omits content from one or more parents. The issuer must hold a `redact` capability on each omitted parent. Redaction from a revoked/quarantined source is denied. A `redaction_attestation` is written so the omission is traceable. Redacted edges are excluded from the transitive source check, which is what makes a redacted summary safe to serve even if the excluded parent is later revoked.

### 4. BFS revocation propagation

`revoke_artifact` uses a breadth-first search over `lineage_edges` to find every `active` or `redacted` descendant. Each is marked `quarantined` and an audit event is written. The BFS is synchronous in the MVP; for large graphs it should be pushed to a background queue.

### 5. Open-weight model placement

BioVault enforces the permission gate **before** any model sees artifact content. The `POST /query` endpoint is an adapter stub that:

1. Resolves the principal (token check).
2. Calls `evaluate_access`.
3. Returns the authorised content blob.

The caller's model runtime then processes the blob. No closed-model dependency is introduced. Any open-weight model compatible with a plain text context window can be used here.

---

## Component map

```
backend/
  app/
    main.py          — all endpoints, evaluate_access, resolve_principal,
                       revoke_artifact, log_audit, init_db, seed
  tests/
    conftest.py      — pytest fixtures, temp DB, seeded tokens
    test_biovault.py — 11 tests covering allow/deny, spoofing, grants,
                       redaction, revocation, audit, latency P99

frontend/
  src/
    App.tsx          — user switcher, artifact panel, lineage panel,
                       ComplianceMatrix, ConceptCards, demo step runner
    App.css          — layout, badges, compliance rows, concept grid

docs/
  ARCHITECTURE.md    — this file
  DEMO_SCRIPT.md     — 2-minute and 30-second scripts
```
