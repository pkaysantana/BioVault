# BioVault Persistence Architecture

## Scope

This document describes BioVault's production persistence path. It does not
claim the current prototype already implements the production store, migrations,
external IAM sync, production key management, or compliance-grade audit.

Current runtime behavior is unchanged: the demo uses SQLite, deterministic
capability checks, source-lineage enforcement, revocation propagation, and audit
logging in the FastAPI backend.

## Production Decision

Postgres is the production source of truth for BioVault persistence.

SQLite remains demo/local only. It is useful for a zero-infrastructure
hackathon flow, but it is not the authority for enterprise memory governance
because it is single-process oriented, weak for concurrent ACL and revocation
updates, unsuitable for production audit retention, and not the right substrate
for transactional tenant-scoped policy state.

Neo4j is deferred. If introduced, it is a read-optimized projection for lineage
exploration only. Neo4j must never become the permission authority, grant
authority, revocation authority, audit authority, or source of plaintext release
decisions.

## System Boundary

```text
Agent or UI
  -> BioVault API (/artifacts/{id}, /query, /derive, /revoke)
  -> deterministic permission engine
  -> PersistenceStore interface
  -> SQLite demo adapter or Postgres production adapter
  -> audit event persisted before response is trusted
```

The product boundary stays BioVault as the gate. Downstream models do not make
permission decisions. The `/query` endpoint is the typed memory tool used by
agents: it returns authorized context only after deterministic access succeeds,
and returns a deny reason plus `request_id` with no plaintext when access fails.

## Production Tables

The production Postgres schema should preserve the current source-lineage
semantics while adding tenant isolation, immutable versioning, closure-table
lineage traversal, policy versions, and operational audit retention.

| Table | Purpose |
|---|---|
| `tenants` | Tenant identity, slug, status, created timestamps. |
| `users` | BioVault principal, tenant, external subject, email, active/deprovisioned state. |
| `agents` | Tenant-scoped agent principals, ownership, and acting-user relationship where applicable. |
| `artifacts` | Stable artifact identity, tenant, current version, type, status, sensitivity. |
| `artifact_versions` | Immutable content metadata, source hash, encrypted payload reference, created_by. |
| `capability_grants` | Subject, artifact, operation, revoked flag, expiry, policy/source version. |
| `lineage_edges` | Parent artifact/version, child artifact/version, inclusion, dependency type, source hash. |
| `artifact_ancestors` | Closure table for included transitive ancestry at scale. |
| `audit_events` | Append-only access decision log. |
| `revocation_events` | Source revoke/quarantine events and affected descendant counts. |
| `policy_versions` | Monotonic policy/source version records. |
| `redaction_attestations` | Governed exception metadata, source hashes, approver, reason. |

## Required Index Strategy

The production adapter should include at least these lookup paths:

```sql
-- Grants: hot path for capability checks.
CREATE INDEX idx_grants_lookup
  ON capability_grants
  (tenant_id, subject_id, artifact_id, operation, revoked, expires_at);

-- Lineage edge traversal and projection repair.
CREATE INDEX idx_lineage_parent
  ON lineage_edges (tenant_id, parent_artifact_id, parent_version_id);

CREATE INDEX idx_lineage_child
  ON lineage_edges (tenant_id, child_artifact_id, child_version_id);

-- Closure table access checks.
CREATE INDEX idx_artifact_ancestors_artifact
  ON artifact_ancestors (tenant_id, artifact_id);

CREATE INDEX idx_artifact_ancestors_ancestor
  ON artifact_ancestors (tenant_id, ancestor_artifact_id);

-- Audit retrieval and correlation.
CREATE INDEX idx_audit_request
  ON audit_events (tenant_id, request_id);

CREATE INDEX idx_audit_artifact
  ON audit_events (tenant_id, artifact_id);

CREATE INDEX idx_audit_principal
  ON audit_events (tenant_id, principal_id);

CREATE INDEX idx_audit_timestamp
  ON audit_events (tenant_id, timestamp);
```

Exact index ordering should be validated against the final workload and query
planner output, but these are the access patterns the production design must
support.

## Revocation Transaction

Production revocation must be atomic. A source revoke cannot partially update
grants without lineage state, or lineage state without audit.

```text
1. Begin transaction.
2. Lock the source artifact/version and relevant grant rows.
3. Mark the source revoked or quarantined.
4. Create a new monotonic policy/source version.
5. Find affected descendants through artifact_ancestors.
6. Quarantine descendants that included the revoked source.
7. Revoke or mark affected grants if required by policy.
8. Append revocation_events and audit_events.
9. Commit.
```

After commit, stale capabilities must deny because the access check observes the
new source status, descendant quarantine state, revoked grant state, or higher
policy/source version.

## Access Check Path

The production hot path remains deterministic and model-free:

```text
1. Resolve the presented token locally to a BioVault principal.
2. Validate tenant, user/agent active state, artifact existence, and artifact status.
3. Check the target artifact grant for the requested operation.
4. For derived artifact reads, check included source ancestor grants.
5. Check revoked or quarantined ancestors.
6. Append an audit event with request_id, principal, artifact, operation,
   decision, reason, latency, policy/source version, and lineage summary.
7. Release plaintext only on allow.
```

No model call and no required IdP network call belongs in this permission hot
path.

## Lineage Performance Path

Small scale can use recursive CTEs over `lineage_edges`. That keeps the model
simple and matches the current prototype's direct source-lineage semantics.

At scale, the Postgres adapter should maintain `artifact_ancestors` as a closure
table for included transitive ancestry. This turns repeated derived-read checks
and revocation fan-out into indexed lookups.

A compiled effective-policy cache can be added later for latency, but only as a
cache of the same source-lineage rule. It must never become an independent trust
path that can release plaintext when the source of truth would deny.

## Adapter Architecture

The backend should move persistence behind a `PersistenceStore` interface before
the Postgres adapter lands.

Required store capabilities:

- Resolve principal from a locally verified token or token-derived subject.
- Read artifacts and immutable artifact versions.
- Check, create, expire, and revoke capability grants.
- Traverse included lineage ancestors and descendants.
- Persist redaction attestations.
- Execute atomic source revocation transactions.
- Append audit events for allow, deny, grant, revoke, derive, redact, and query.
- Expose latency and decision metrics without logging plaintext.

Adapters:

| Adapter | Role |
|---|---|
| SQLite demo adapter | Local/demo adapter that preserves current behavior and fast setup. |
| Postgres adapter | Future production authority for persistence, grants, lineage, revocation, audit, policy versions, and redaction attestations. |
| Neo4j projection adapter | Optional future read projection for lineage exploration only. |

## Conformance Tests

The same behavioral scenarios must pass against the SQLite demo adapter and the
Postgres production adapter:

- Revocation is atomic and denies stale capabilities after source revoke.
- Derived artifact access requires target grant plus included source ancestor grants.
- Revoked or quarantined included ancestors deny derived reads.
- Denied direct reads and `/query` calls return no plaintext/context.
- Audit rows exist for allow, deny, grant, revoke, derive, redact, and query decisions.
- Redaction requires explicit authority, source hashes, attestation, and audit.
- Permission checks remain under the sub-200ms P99 target when measured
  separately from model generation.

## Non-Claims

This document does not claim:

- The Postgres adapter is implemented.
- The current SQLite demo is production security.
- External IAM or source ACL sync is implemented.
- Production KMS/HSM, envelope encryption, or tamper-evident audit is implemented.
- BioVault is clinical decision support or a regulated medical device.
