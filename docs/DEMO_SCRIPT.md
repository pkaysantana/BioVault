# BioVault Demo Script

> Audience: Hackathon judges reviewing the **BasedAI Enterprise Memory Governance at Scale** track.
>
> Scenario: An AI science agent in a pharma R&D workspace derives a Phase II readiness memo from four sensitive source documents. One source is later revoked. This demo shows that BioVault automatically quarantines the derived artifact without touching any role policy — and does so in milliseconds, without a model call.

---

## Setup (30 seconds before you start)

1. Start backend: `uvicorn app.main:app --reload` (port 8000)
2. Start frontend: `npm run dev` (port 5173)
3. Open `http://localhost:5173` — the dashboard auto-seeds on load.
4. If the artifact list is empty, click **↺ Seed / Reset Demo**.
5. Point out the **Flow Banner** at the top of the dashboard:
   `Bearer token → resolve_principal() → evaluate_access() → log_audit() → Decrypt (allow only)`
   This is the entire permission path — no model call anywhere in that chain.

---

## 2-minute demo script

### [0:00–0:20] Introduce the problem

> "BioVault asks: what happens when an AI agent derives a Phase II readiness memo from four source documents, and then one of those source documents — the adverse event memo — is revoked due to a data integrity finding? Standard role-based access control has no answer. BioVault does."

Point to the **Concept Cards**:
- *"RBAC controls users. BioVault controls artifacts and their descendants."*
- *"Revoking a source quarantines downstream derived artifacts."*

Point to the **Flow Banner**: "This is the entire permission path. Bearer token in, decision out. No model."

> **BasedAI requirement addressed:** Agent-level memory governance; no LLM in the governance path.

---

### [0:20–0:40] Step 1 — CEO opens Phase II memo (ALLOW)

Click **Step 1** in the Guided Demo panel.

> "CEO Avery Chen presents their capability token. The server hashes it, looks up the principal, checks that Avery holds a `read` grant on the Phase II memo, and verifies that all four source artifacts are active. Decision: ALLOW. Content is decrypted and shown in the Access Check panel."

Point to the **Access Check** panel — green `allow` banner, `capability_and_lineage_valid`, latency in single-digit milliseconds.

> **BasedAI requirement addressed:** Artifact-level capability check; lineage integrity enforced on every read.

---

### [0:40–0:55] Step 2 — External CRO is denied (DENY)

Click **Step 2**.

> "Owen Brooks, the external CRO, presents his token. He has read access to the public target paper and the CRO assay report — but no capability grant on the Phase II memo. The check returns `missing_capability_grant`. No content is returned."

Point to the **Access Check** panel — red `deny` banner, content `withheld`.

> **BasedAI requirement addressed:** Capability-bound identity prevents access without an explicit grant. A role like "external CRO" grants nothing by itself.

---

### [0:55–1:05] Step 3 — Regulatory Lead is allowed (ALLOW)

Click **Step 3**.

> "Nora Singh, the Regulatory Lead, does hold a read grant on the Phase II memo. Identical check, different grant, different outcome. Deterministic."

> **BasedAI requirement addressed:** Capability grants are per-artifact and per-principal — same artifact, different result for different principals.

---

### [1:05–1:30] Step 4 — Revoke the adverse event memo

Click **Step 4**.

> "Now I revoke the adverse event memo — imagine a safety pharmacology reviewer flagged a data integrity error. Watch the lineage panel."

After the step completes, point to the status message and the **Lineage** panel:

> "The backend traversed the lineage graph using BFS. Phase II Readiness Memo — derived from the adverse event memo — is now quarantined. So is the Exec Brief derived from the Phase II memo. Two artifacts quarantined automatically, zero role changes, zero model calls."

> **BasedAI requirement addressed:** Source revocation propagation; lineage-aware access control.

---

### [1:30–1:45] Step 5 — CEO is now denied

Click **Step 5**.

> "Avery Chen — the CEO, who was allowed 90 seconds ago — is now denied. Reason: `derived_from_revoked_source`. Not because their role changed. Because the artifact is quarantined by lineage. The amber badges in the artifact list show which artifacts are affected."

Point to the amber `quarantined` badges in the **Artifacts** panel.

> **BasedAI requirement addressed:** Revocation propagation is immediate and automatic; no cache TTL, no eventual consistency.

---

### [1:45–2:00] Step 6 — Audit log and compliance matrix

Click **Step 6**, then scroll to the **Compliance Matrix** and **Audit Log**.

> "Every decision — allow, deny, revoke, derive — is recorded as a structured audit event. The `Req ID` column shows a truncated `request_id` for each row. Click any audit row to expand its structured provenance: `purpose`, `grant_id` (the specific capability grant that was used), `principal`, `lineage_checked`, and `lineage_decision`. Grant and revoke events also carry `issuer`, `subject`, `scope`, and `attestation_id`."

Point to the `Req ID` column — every decision is traceable by ID.
Click one audit row to expand it. Point to `grant_id` and `purpose` in the detail.

> "The compliance matrix now shows the nature of each claim. TESTED rows are backed by a named pytest. CODE rows are backed by a static code inspection. The two LIVE rows — revocation propagation and audit logs with provenance — flip to LIVE when you can see the evidence live in this session. P99 is a live measurement — well under the 200ms budget, because the permission path is indexed SQL, not a model."

Point to the TESTED / CODE / LIVE / PASS badges. Point to the live P99 value.

> **BasedAI requirement addressed:** Auditability with structured provenance; sub-200ms governance latency.

---

## 30-second fallback demo

*Use this if you only have 30 seconds with a judge.*

> "BioVault is a capability-secured artifact memory layer for AI science agents. Three things RBAC cannot do:
>
> **One** — access is per artifact, not per role. The Phase II readiness memo has its own capability grants, independent of job title. [point to flow banner]
>
> **Two** — lineage is tracked. When I revoke this adverse event memo [click Step 4], watch: Phase II memo and everything derived from it is automatically quarantined.
>
> **Three** — no model decides any of this. The permission check is pure SQL and Python. An open-weight model — Qwen, Llama, Mistral, whatever — only ever sees content after the permission gate passes."

*(30 seconds, covers capability-bound identity, revocation propagation, and LLM-free governance)*

---

## Common judge questions

**Q: How is this different from document-level ACLs?**
A: ACLs are static and flat. BioVault's lineage check is dynamic — revoking a source propagates quarantine to all derived descendants regardless of depth. ACLs have no concept of "this artifact was built from that artifact."

**Q: What stops someone from bypassing the token check?**
A: `resolve_principal()` is a FastAPI `Depends()` on every protected route. There is no fallback: no `?user_id=` override, no default principal. The test `test_user_id_query_param_is_not_authority` verifies that passing `?user_id=u_ceo` without a valid token returns HTTP 401, not the CEO's content.

**Q: Can you use a real open-weight model with this?**
A: Yes. `POST /query` is the agent gate. The model calls this endpoint with its bearer token before generating any response. If the decision is `allow`, `plaintext_content` is returned. If `deny`, no content is returned and the model must not generate from that artifact. No model is imported in the backend — `grep -r "openai\|anthropic\|langchain" backend/app/` returns nothing.

**Q: How does governed redaction work?**
A: Creating a `redacted` derived artifact requires the `redact` capability on every parent. Deriving from a revoked source is denied entirely — redaction cannot launder compromised data. A redaction attestation records the source hashes, included/excluded parents, reason, and `request_id` for audit purposes.

**Q: What's the performance cost of lineage integrity checks?**
A: The lineage check is a depth-first SQL traversal over an indexed `lineage_edges` table. For the demo dataset (8 artifacts, 4 lineage edges), P99 is under 2ms. The test `test_permission_latency_p99_under_200ms` runs 200 permission checks against a seeded dataset and asserts P99 < 200ms.
