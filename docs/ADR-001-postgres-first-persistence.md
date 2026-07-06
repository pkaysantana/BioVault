# ADR-001: Postgres-First Production Persistence

## Status

Proposed for the production path. Not implemented in runtime code.

## Date

2026-07-04

## Context

BioVault currently demonstrates deterministic artifact governance with SQLite.
The prototype proves the core rule: artifact reads and `/query` calls are denied
unless the principal has the target capability and, for derived artifacts, the
required included source-lineage grants. Revoking a source quarantines derived
descendants and audit events record the decision path.

That is adequate for a hackathon demo, but production enterprise memory
governance needs transactional concurrency, tenant-scoped migrations, durable
audit retention, indexed permission checks, atomic revocation, and a clean path
for IAM and source ACL synchronization.

## Decision

BioVault will use Postgres as the production source of truth for:

- Tenants.
- Users and agent principals.
- Artifacts and immutable artifact versions.
- Capability grants.
- Lineage edges.
- Included transitive ancestor closure.
- Revocation events.
- Audit events.
- Policy/source versions.
- Redaction attestations.

SQLite remains demo/local only.

Neo4j is deferred. If added, it is a read-optimized projection for lineage
exploration only. It must not decide permission, grant authority, revocation,
audit truth, or plaintext release.

## Consequences

- The production adapter needs migrations, schema versioning, and rollback
  discipline.
- Revocation must run in a single database transaction that updates source
  status, descendant quarantine state, grants if required, policy/source version,
  revocation event rows, and audit rows.
- Permission checks need indexed grant lookups and indexed lineage/closure
  lookups.
- A `PersistenceStore` interface should isolate the permission engine from the
  storage implementation.
- Adapter conformance tests must run the same permission scenarios against the
  SQLite demo adapter and the Postgres adapter.
- The production benchmark target remains sub-200ms P99 for permission checks,
  measured separately from any model generation.
- No runtime behavior changes until the Postgres adapter is implemented.

## Production Schema Direction

The initial Postgres model should include:

| Table | Purpose |
|---|---|
| `tenants` | Tenant identity, slug, status, created timestamps. |
| `users` | BioVault principal, tenant, external subject, email, active/deprovisioned state. |
| `agents` | Tenant-scoped agent principals and ownership. |
| `artifacts` | Stable artifact identity, tenant, current version, type, status, sensitivity. |
| `artifact_versions` | Immutable content metadata, source hash, encrypted payload reference, created_by. |
| `capability_grants` | Subject, artifact, operation, revoked flag, expiry, policy/source version. |
| `lineage_edges` | Parent artifact/version, child artifact/version, inclusion, dependency type, source hash. |
| `artifact_ancestors` | Closure table for included transitive ancestry. |
| `audit_events` | Append-only access decision log. |
| `revocation_events` | Source revoke/quarantine events and affected descendant counts. |
| `policy_versions` | Monotonic policy/source version records. |
| `redaction_attestations` | Governed exception metadata, source hashes, approver, reason. |

Required indexes are documented in
[PERSISTENCE_ARCHITECTURE.md](PERSISTENCE_ARCHITECTURE.md).

## Revocation Requirement

Production revocation must be atomic:

```text
revoke source
  -> increment policy/source version
  -> quarantine included descendants through artifact_ancestors
  -> revoke or mark affected grants if required
  -> append revocation and audit events
  -> commit
```

After commit, stale capabilities must deny. A caller must not be able to race a
revocation and receive plaintext from an artifact derived from a revoked source.

## Non-Claims

This ADR does not claim:

- Postgres persistence is already implemented.
- SQLite is production-ready.
- External IAM, SCIM, source ACL, KMS/HSM, or tamper-evident audit is already implemented.
- BioVault is production security today.
- BioVault is clinical decision support.

## Related Documents

- [PERSISTENCE_ARCHITECTURE.md](PERSISTENCE_ARCHITECTURE.md)
- [ADR-002-oidc-scim-entra-first.md](ADR-002-oidc-scim-entra-first.md)
- [AGENT_TOOL_CONTRACT.md](AGENT_TOOL_CONTRACT.md)
