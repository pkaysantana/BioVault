# BioVault Demo Script

> Audience: Hackathon judges reviewing the **BasedAI Enterprise Memory Governance at Scale** track.

Two demo scenarios are available. **The default is the SME / company-memory payroll-leakage story**, which maps directly to the workshop use case BasedAI described: a marketing person accidentally asks about costs and leaks payroll. The biotech scenario (AI science / pharma R&D) is available as a secondary demo via the scenario switcher.

---

## Setup (30 seconds before you start)

1. Start backend: `uvicorn app.main:app --reload` (port 8000)
2. Start frontend: `npm run dev` (port 5173)
3. Open `http://localhost:5173` — the dashboard auto-seeds the SME scenario on load.
4. If the artifact list is empty, click **↺ Seed / Reset Demo**.
5. Point out the **Flow Banner**:
   `Bearer token → resolve_principal() → evaluate_access() → log_audit() → Decrypt (allow only)`
   This is the entire permission path — no model call, no LLM sensitivity filter anywhere in that chain.

---

## Default scenario: SME / company-memory payroll leakage

### The problem

> "A marketing manager asks an AI agent: 'Show me our Q3 cost breakdown.' The agent retrieves a quarterly growth margin report that was derived from campaign costs, vendor contracts — and payroll data. Marketing accidentally sees everyone's salaries."

This is the failure mode BasedAI's workshop described. BioVault prevents it without LLM-based sensitivity filtering, without duplicated file silos, and without role-level policies.

### Why NOT the alternatives?

Point to the **Comparison Cards** on the dashboard:

- **Old approach — duplicate into team silos:** Finance and Marketing each get a copy. Changes don't sync. A payroll file in a shared folder becomes invisible to governance. You cannot revoke a copy you don't track.
- **Old approach — LLM sensitivity filtering:** Route every retrieval through a model to classify sensitivity and decide access. Token-heavy. Latency compounds. Models can be confused. Not a security boundary.
- **BioVault:** One global artifact store. Deterministic capability check at every read. Zero model tokens in the permission path.

---

## 2-minute demo script (SME)

### [0:00–0:15] Introduce the problem

> "Marketing has access to campaign costs and vendor contracts. They should NOT see the Q3 growth margin report — because it's a derived artifact that includes payroll data. How do we enforce that without copying files everywhere, without role-label gymnastics, and without routing every query through an LLM sensitivity filter?"

Point to the **Comparison Cards**. Point to the **Flow Banner**: "Zero model tokens here."

---

### [0:15–0:30] Step 1 — Marketing opens Campaign Cost Summary (ALLOW)

Click **Step 1**.

> "Morgan Chen, the Marketing Manager, presents a capability token. The server hashes it, resolves the principal, checks that Morgan holds a `read` grant on Campaign Cost Summary. ALLOW. Content shown."

Point to the green `allow` banner in the **Access Check** panel.

---

### [0:30–0:45] Step 2 — Marketing attempts Q3 Growth Margin Report (DENY)

Click **Step 2**.

> "Same principal, different artifact. Morgan asks for the Q3 Growth Margin Report — a derived artifact synthesised from campaign costs, vendor contracts, and payroll data. Marketing lacks a capability grant on this governed derived artifact. DENY. No content returned."

Point to the red `deny` banner. Point out `missing_capability_grant`. Point to the empty content area.

> **Key point:** This is NOT LLM-based sensitivity filtering. This is a deterministic capability check against a specific artifact ID. Zero model tokens consumed.

---

### [0:45–1:00] Step 3 — Finance opens Q3 Growth Margin Report (ALLOW)

Click **Step 3**.

> "Jordan Lee, the Finance Lead, presents their token. Finance holds a read grant on the Q3 report. Identical permission pipeline, different outcome. Decision: ALLOW. Content decrypted."

> **Comparison with RBAC:** Finance and Marketing both have "employee" access to the company knowledge base. BioVault doesn't use their role label at all — only the specific capability grant on the specific artifact.

---

### [1:00–1:10] Step 4 — Inspect lineage

Click **Step 4**.

> "The Q3 Growth Margin Report is derived from three sources: Campaign Cost Summary, Vendor Contracts, and Payroll Salary Register. Look at the Lineage panel. All three sources show as `included` edges. This means if any one of them is revoked, the derived report must become inaccessible."

Point to the **Lineage** panel showing the three parent artifacts.

---

### [1:10–1:25] Step 5 — Owner revokes Payroll Salary Register

Click **Step 5**.

> "Imagine the HR team flags a data integrity issue with the payroll register — maybe the file was exported incorrectly. The Owner revokes it. Watch the status message."

After the step completes, point to the status message and the artifact list:

> "payroll_salary_register is now revoked. Q3 Growth Margin Report — the derived artifact — is automatically quarantined. The BFS traversal found every active derived descendant and quarantined them. Zero role changes. Zero model calls."

Point to the amber `quarantined` badge on Q3 Growth Margin Report.

---

### [1:25–1:35] Step 6 — Show quarantine state

Click **Step 6**.

> "The Q3 report badge shows quarantined. The Lineage panel shows the revoked payroll source. The artifact is sealed — any read will be denied regardless of who tries."

---

### [1:35–1:50] Step 7 — Finance is now denied

Click **Step 7**.

> "Jordan Lee — Finance, who was allowed 45 seconds ago — is now denied. Reason: `derived_from_revoked_source`. Not because their role changed. Because the artifact is quarantined by lineage. Payroll revocation propagated automatically."

Point to the red `deny` banner. Point to `derived_from_revoked_source`.

---

### [1:50–2:00] Step 8 — Audit log and evidence

Click **Step 8**. Scroll to the **Audit Log**.

> "Every decision is logged. Click any row to expand it. You'll see `request_id`, `principal`, `operation`, `decision`, `reason`, `purpose`, `grant_id` (the specific capability grant used), `lineage_checked`, `latency_ms`. The compliance matrix P99 is a live measurement. It's single-digit milliseconds — because the permission path is indexed SQL, not a model."

Point to TESTED / CODE EVIDENCE / LIVE badges. Point to the live P99 value.

---

## 30-second fallback demo

> "BioVault is a capability-secured company memory layer. Three things LLM sensitivity filtering cannot do:
>
> **One** — access is per artifact, not per role. Marketing's job title is irrelevant. Only a capability grant on the specific artifact grants access. [point to the deny banner for Marketing on the Q3 report]
>
> **Two** — lineage is tracked. The Q3 Growth Margin Report was derived from payroll data. When I revoke payroll [click Step 5], the derived report is quarantined automatically — two operations, zero model calls.
>
> **Three** — the permission path uses zero model tokens. [point to the '0 model tokens' badge in the Comparison Cards] The check is pure SQL. Any open-weight model runtime can call POST /query and get a deterministic allow or deny before it generates anything."

*(30 seconds, covers capability-bound identity, lineage-aware revocation, and LLM-free governance)*

---

## Secondary scenario: AI Science / Biotech

Switch to the biotech scenario using the **scenario switcher** in the hero section. This re-seeds with a pharma R&D dataset (kinase drug program BVK-14) and restores the original 6-step demo:

| Step | Who | Action | Expected |
|---|---|---|---|
| 1 | CEO (Avery Chen) | Open Phase II Readiness Memo | **ALLOW** — content decrypted |
| 2 | External CRO (Owen Brooks) | Open Phase II Readiness Memo | **DENY** — missing_capability_grant |
| 3 | Regulatory Lead (Nora Singh) | Open Phase II Readiness Memo | **ALLOW** — sources healthy |
| 4 | CEO | Revoke Adverse Event Memo | Derives exec brief, then revokes; quarantine cascades to 2 artifacts |
| 5 | CEO | Open Phase II Readiness Memo | **DENY** — derived_from_revoked_source |
| 6 | — | Review audit log + compliance matrix | Every decision logged; P99 shown live |

The biotech scenario demonstrates the same governance primitives in an AI science context: derived clinical memos quarantined when source data is revoked.

---

## Common judge questions

**Q: How is this different from document-level ACLs?**
A: ACLs are static and flat. BioVault's lineage check is dynamic — revoking a source propagates quarantine to all derived descendants regardless of depth. ACLs have no concept of "this artifact was built from that artifact." Revoke a source in BioVault and every downstream derived artifact is sealed without touching a single ACL.

**Q: How is this different from LLM-based sensitivity filtering?**
A: LLM sensitivity filtering makes every retrieval go through a model to classify the content and decide whether to return it. This is token-heavy (every retrieval costs tokens), non-deterministic (the model can be confused or prompted), has latency that compounds with document volume, and is not a security boundary — a model can be jailbroken. BioVault's permission path is pure SQL: deterministic, sub-millisecond, zero model tokens, and audited with a structured `request_id` on every decision.

**Q: What stops someone from bypassing the token check?**
A: `resolve_principal()` is a FastAPI `Depends()` on every protected route. There is no fallback: no `?user_id=` override, no default principal. The test `test_user_id_query_param_is_not_authority` verifies that passing `?user_id=u_owner` without a valid token returns HTTP 401.

**Q: Why not just copy files into team silos?**
A: Copies break governance. If Finance has a copy of the payroll file and you revoke the original, the copy is still live. BioVault uses a single canonical artifact store — every team reads from the same artifact under their own capability grant. No copies, no drift, no orphaned data.

**Q: Can you use a real open-weight model with this?**
A: Yes. `POST /query` is the agent gate. The model calls this endpoint with its bearer token before generating any response. If the decision is `allow`, `plaintext_content` is returned. If `deny`, no content is returned and the model must not generate from that artifact. No model is imported in the backend — `grep -r "openai\|anthropic\|langchain" backend/app/` returns nothing.

**Q: What's the performance cost of lineage integrity checks?**
A: The lineage check is a depth-first SQL traversal over an indexed `lineage_edges` table. For the demo dataset, P99 is under 2ms. The test `test_permission_latency_p99_under_200ms` runs 200 permission checks and asserts P99 < 200ms.
