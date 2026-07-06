# BioVault Agent Tool Contract

## Positioning

BioVault is a memory governance tool, not an agent and not a model. It does not
generate. It returns authorized context or a denial.

BioVault is model-agnostic. Agents call it as a typed memory tool. The
permission decision is deterministic; downstream open-weight generation only
happens after BioVault returns allow.

```text
agent -> POST /query -> BioVault deterministic gate -> allow/deny
```

Open-weight models may consume `authorized_context` after allow. They never
decide permission, and no model call is in the permission path.

## Runtime Flow

`POST /query` is the agent-facing retrieval gate:

1. Resolve the bearer capability token to a BioVault principal.
2. Check the target artifact grant.
3. Check artifact status.
4. For derived artifacts, check included source-lineage grants.
5. Check revoked or quarantined ancestors.
6. Write audit with `request_id`.
7. Return `authorized_context` only on allow.

Denied responses return `authorized_context: null` and no plaintext, context,
synthesis, source text, hidden artifact body, or parent source plaintext.

## Canonical Result

```ts
type BioVaultDecision = "allow" | "deny";

type BioVaultQueryResult = {
  decision: BioVaultDecision;
  reason: string;
  request_id: string;
  audit_ref: {
    request_id: string;
    operation: "query";
    artifact_id: string;
    principal: string;
    decision: BioVaultDecision;
  };
  authorized_context: null | {
    artifact_id: string;
    title: string;
    content: string;
    sensitivity: string;
    lineage: {
      included_sources: string[];
      redacted_sources: string[];
      revoked_sources: string[];
    };
  };
  lineage_metadata: {
    requires_target_grant: true;
    requires_included_source_grants: boolean;
    included_source_count?: number;
    blocked_source_artifact_id?: string;
    missing_source_artifact_id?: string;
  };
};
```

## Allow Example

```json
{
  "decision": "allow",
  "reason": "capability_and_lineage_valid",
  "request_id": "req_abc123",
  "audit_ref": {
    "request_id": "req_abc123",
    "operation": "query",
    "artifact_id": "phase2_readiness_memo",
    "principal": "u_regulatory",
    "decision": "allow"
  },
  "authorized_context": {
    "artifact_id": "phase2_readiness_memo",
    "title": "Phase II Readiness Memo",
    "content": "DERIVED - authorized scientific context...",
    "sensitivity": "confidential",
    "lineage": {
      "included_sources": [
        "adverse_event_memo",
        "internal_sar_table",
        "public_target_paper",
        "toxicity_report"
      ],
      "redacted_sources": [],
      "revoked_sources": []
    }
  },
  "lineage_metadata": {
    "requires_target_grant": true,
    "requires_included_source_grants": true,
    "included_source_count": 4
  }
}
```

## Deny Example

```json
{
  "decision": "deny",
  "reason": "missing_capability_grant",
  "request_id": "req_def456",
  "audit_ref": {
    "request_id": "req_def456",
    "operation": "query",
    "artifact_id": "phase2_readiness_memo",
    "principal": "u_cro",
    "decision": "deny"
  },
  "authorized_context": null,
  "lineage_metadata": {
    "requires_target_grant": true,
    "requires_included_source_grants": true
  }
}
```

## Agent Adapter Pattern

```python
result = biovault.query(
    artifact_id="phase2_readiness_memo",
    bearer_token=agent_token,
    purpose="agent_retrieval",
)

if result.decision == "allow":
    return downstream_runtime.run(result.authorized_context["content"])

return "Denied - no synthesis from protected scientific memory."
```

The model/runtime adapter is downstream only. It may point to a BasedAPIs-style
open-weight endpoint, Ollama, or another open-weight runtime after
authorization. This repo does not implement or claim a live BasedAPIs or model
integration.

## Non-Claims

This document does not claim:

- A live BasedAPIs integration exists.
- A model call is implemented in the permission path.
- Ollama is required for the demo.
- Open-weight generation changes BioVault's permission decision.
- Denied artifacts can be summarized or synthesized without authorized context.
- BioVault is production security or clinical decision support.
