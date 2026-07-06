# ADR-002: OIDC + SCIM IAM Layer, Microsoft Entra First

## Status

Proposed for the production path. Not implemented in runtime code.

## Date

2026-07-04

## Context

The current demo resolves principals from seeded capability tokens and stores
only token hashes. That is appropriate for a local prototype, but enterprise
deployment needs standards-based identity, directory provisioning, group and
membership synchronization, deprovisioning, source ACL events, and local
authorization decisions that do not require calling the IdP during every
permission check.

BioVault must stay model-agnostic and provider-portable. Identity providers
prove who the principal is and what directory state is known. BioVault still
owns artifact authorization, lineage rules, revocation state, redaction
exceptions, and audit.

## Decision

BioVault will define a generic OIDC + SCIM IAM layer.

Microsoft Entra is the first concrete enterprise provider profile because it
matches Microsoft 365-centered enterprise R&D and CRO environments. Auth0 and
Okta can fit later through the same generic OIDC + SCIM adapter shape, but they
are not the first production profile.

IdP claims are inputs only. Group claims must never directly release artifact
plaintext. A caller receives artifact content only when BioVault's
`CapabilityPolicyEngine` allows the target artifact and required source-lineage
checks.

## Interfaces

### OIDCProvider

Validates identity tokens and maps them to BioVault principals.

Responsibilities:

- Validate issuer.
- Validate audience.
- Validate expiry and not-before claims.
- Validate token signature against JWKS.
- Handle signing-key rotation.
- Map stable external identity fields such as `sub`, Entra `oid`, and email to
  a tenant-scoped BioVault principal.
- Reject tokens from unknown tenants, unknown client IDs, inactive users, or
  unsupported assurance contexts.

### SCIMDirectoryProvider

Synchronizes directory state into BioVault's local store.

Responsibilities:

- Sync users.
- Sync groups.
- Sync external IDs.
- Sync group membership.
- Track active/deprovisioned state.
- Record source directory version or sync cursor where supported.
- Ensure deprovisioned users and removed group memberships stop contributing to
  future BioVault decisions.

### SourceACLProvider

Future provider for upstream scientific source systems such as SharePoint,
Google Drive, ELN, LIMS, eTMF, and document-management systems.

Responsibilities:

- Import source ACL snapshots.
- Consume source revoke, quarantine, and membership-change events.
- Map source documents to BioVault artifacts or artifact versions.
- Emit source policy versions used by access checks and audit.

This is future work. The current prototype simulates source revocation.

### CapabilityPolicyEngine

BioVault-owned authorization layer.

Responsibilities:

- Evaluate artifact grants.
- Enforce source-lineage access for derived artifacts.
- Enforce revoked/quarantined ancestor denial.
- Enforce redaction attestation rules.
- Compare policy/source versions where needed.
- Produce deterministic allow/deny decisions with reasons.

### AuditLogger

Append-only decision logging interface.

Required fields:

- `request_id`.
- Principal.
- Artifact.
- Operation.
- Decision.
- Reason.
- Latency.
- Policy/source version.
- Source-lineage summary where applicable.

Audit records must not include plaintext artifact content.

## Microsoft Entra Provider Profile

The Entra profile should use the Microsoft identity platform OIDC metadata
document and JWKS endpoint for token validation. Microsoft documents the
tenant-scoped authority as `https://login.microsoftonline.com/{tenant}/v2.0`,
the metadata path as `/.well-known/openid-configuration`, and the JWKS path as
`/discovery/v2.0/keys`:

- https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc

For directory provisioning, the Entra profile should support SCIM user and
group operations, including `/Users`, `/Groups`, membership updates, and the
`active` flag for disable/deprovision flows:

- https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups

## Production Access Flow

```text
1. OIDC token is validated locally by OIDCProvider.
2. External identity maps to a tenant-scoped BioVault user or agent.
3. SCIMDirectoryProvider-maintained state confirms active principal and current memberships.
4. SourceACLProvider-maintained state contributes source policy versions when available.
5. CapabilityPolicyEngine checks BioVault artifact grants and source-lineage requirements.
6. AuditLogger records allow or deny with request_id, reason, latency, and policy/source version.
7. Plaintext is released only on allow.
```

No required IdP network call and no model call belongs in the hot permission
path.

## Consequences

- BioVault remains portable across identity providers that support OIDC and
  SCIM.
- Entra becomes the first enterprise integration profile because it matches the
  most likely customer IAM environment.
- Group claims are treated as directory facts, not permission decisions.
- Source ACL and deprovision events must update local BioVault policy state
  before they can affect deterministic access checks.
- Audit events need enough provider/source version context to explain why a
  decision was made at that time.

## Non-Claims

This ADR does not claim:

- OIDC validation is implemented in the current demo.
- SCIM provisioning is implemented.
- Microsoft Entra integration has been tested with real credentials.
- Auth0 integration exists.
- Source ACL sync exists for SharePoint, Drive, ELN, LIMS, or eTMF.
- Production KMS/HSM or compliance-grade audit is implemented.
- BioVault is clinical decision support.

## Related Documents

- [PERSISTENCE_ARCHITECTURE.md](PERSISTENCE_ARCHITECTURE.md)
- [ADR-001-postgres-first-persistence.md](ADR-001-postgres-first-persistence.md)
- [AGENT_TOOL_CONTRACT.md](AGENT_TOOL_CONTRACT.md)
