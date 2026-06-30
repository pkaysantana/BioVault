# BioVault Demo Script

> Audience: Hackathon judges reviewing the BasedAI Enterprise Memory Governance track.

---

## Setup (30 seconds before you start)

1. Start backend: `uvicorn app.main:app --reload` (port 8000)
2. Start frontend: `npm run dev` (port 5173)
3. Open `http://localhost:5173` — you should see the BioVault dashboard.
4. If the artifact list is empty, click **Seed Demo Data** to initialise.

---

## 2-minute demo script

### [0:00–0:20] Introduce the problem

> "BioVault asks: what happens when an AI agent derives a Phase II readiness memo from a set of source documents, and then one of those source documents — say, an adverse event memo — is revoked? Standard role-based access control has no answer. BioVault does."

Point to the **Concept Cards** section:
- "RBAC controls users. BioVault controls artifacts and their descendants."
- "Revoking a source quarantines downstream derived artifacts."

---

### [0:20–0:40] Step 1 — CEO opens the Phase II memo (ALLOW)

Click **Step 1** in the Guided Demo panel.

> "CEO Avery Chen holds a `read` capability on the Phase II Readiness Memo. All four source artifacts are active. Decision: ALLOW. Content is decrypted and shown."

Point to the artifact panel — status badge `active`, content visible.

---

### [0:40–0:55] Step 2 — External CRO is denied (DENY)

Click **Step 2**.

> "Owen Brooks, our external CRO, has no capability grant on the Phase II memo. The permission check returns `missing_capability_grant`. No content is returned — not even a partial view."

Point to the artifact panel — decision `DENY`, content empty.

---

### [0:55–1:05] Step 3 — Regulatory Lead is allowed (ALLOW)

Click **Step 3**.

> "Nora Singh, Regulatory Lead, does hold a read grant. Allowed. The same deterministic check, a different outcome — purely because the capability grant exists."

---

### [1:05–1:30] Step 4 — Revoke the adverse event memo

Click **Step 4**.

> "Now I'll revoke the adverse event memo — imagine a safety review found a data integrity issue. Watch what happens downstream."

After the step completes, point to the status message:
> "The backend ran a BFS over the lineage graph. Phase II Readiness Memo and the Exec Brief derived from it are now quarantined — automatically, without touching the user's role or re-evaluating every policy rule."

---

### [1:30–1:45] Step 5 — CEO is now denied

Click **Step 5**.

> "The CEO — who was allowed just 90 seconds ago — is now denied. Not because their role changed. Because the artifact is quarantined. Reason: `derived_from_revoked_source`."

Point to the amber `quarantined` badges in the artifact list.

---

### [1:45–2:00] Step 6 — Audit log and compliance matrix

Click **Step 6**, then scroll to the **Compliance Matrix** and **Audit Log**.

> "Every decision — allow and deny — is recorded with a request ID, principal ID, reason, and latency. The compliance matrix shows all nine requirements. P99 latency is live — it stays well under 200 milliseconds because we use indexed SQL, not a model call."

Point to the live P99 value in the Compliance Matrix.

> "No LLM was called at any point in that permission flow. The model sits outside the boundary. BioVault is the gate."

---

## 30-second fallback demo

*Use this if you only have 30 seconds with a judge.*

> "BioVault is a capability-secured artifact memory layer. It does three things RBAC cannot:

> **One** — access is per artifact, not per role. The Phase II memo has its own capability grants, independent of job title.

> **Two** — lineage is tracked. When I revoke this adverse event memo — [click Revoke button] — watch: the Phase II memo, which was derived from it, is automatically quarantined.

> **Three** — no model decides any of this. The permission check is pure SQL and Python. The open-weight model — Qwen, Llama, Mistral, whatever you want — only sees content after the permission gate passes."

*(30 seconds, covers the three core differentiators)*

---

## Common judge questions

**Q: How is this different from document-level ACLs?**
A: ACLs are static. BioVault's lineage check is dynamic — when a source is revoked, every derived artifact is automatically quarantined, no matter how deep the lineage graph is.

**Q: What stops a developer from bypassing the token check?**
A: `resolve_principal()` is a FastAPI dependency on every protected route. The only query string parameter is `?user_id=` for the GET /users listing, which has no authority over access decisions. The tests include `test_user_id_query_param_is_not_authority` that verifies this.

**Q: Can you use a real open-weight model with this?**
A: Yes. `POST /query` is the agent gate. Pass the bearer token, get plaintext content back if allowed. The model calls this before generating any response. No model is imported in the backend — see `grep -r "openai\|anthropic\|langchain" backend/app/` — it returns nothing.

**Q: How does governed redaction work?**
A: Deriving a `redacted` artifact requires the `redact` capability on every parent. Deriving from a revoked source is denied entirely — redaction cannot launder bad data. A redaction attestation records the source hashes and who authorised it.
