# BioVault Demo Script

> Audience: Hackathon judges · **BasedAI Enterprise Memory Governance at Scale**

**BioVault is lineage-secured artifact memory for AI science agents.** The demo is the BVK-14 kinase programme: derived Phase II memos, external CRO denial, adverse-event revocation with lineage quarantine.

---

## Setup (30 seconds)

1. Backend: `uvicorn app.main:app --reload` (port 8000)
2. Frontend: `npm run dev` (port 5173)
3. Open `http://localhost:5173` — biotech demo auto-seeds on load
4. If empty, click **↺ Seed / Reset Demo**
5. Point to **Flow Banner**: `Bearer token → resolve_principal() → evaluate_access() → log_audit() → Decrypt (allow only)` — no LLM in this chain

---

## The problem (15 sec)

> "An AI science agent synthesises a Phase II Readiness Memo from toxicity data, SAR tables, and an adverse-event memo. An external CRO must not access that derived memo. When the adverse-event source is revoked for data integrity, every derived clinical artifact that included it must quarantine — automatically, auditable, without routing access decisions through an LLM."

### Why NOT the alternatives?

Point to **Comparison Cards**:

- **Silo copies:** Duplicate lab, CRO, regulatory, and clinical files into separate folders — revoke the canonical source, stale copies persist
- **LLM filtering:** Token-heavy sensitivity filtering over clinical/scientific content — extra model calls, non-deterministic, not a security boundary
- **BioVault:** One shared scientific memory, capability per artifact, lineage propagation, **0 model tokens in permission path**

---

## 2-minute demo script (8 steps)

### [0:00–0:15] Intro

> "BioVault secures AI-generated scientific artifacts by carrying source permissions through lineage. I'll show deterministic allow/deny on a derived Phase II memo — and what happens when we revoke an adverse-event source."

### [0:15–0:25] Step 1 — Regulatory Lead opens Phase II Readiness Memo (ALLOW)

Click **Step 1**.

> "Nora Singh, Regulatory Lead. Capability token resolved. Read grant on `phase2_readiness_memo`. ALLOW — content decrypted."

Green `allow` banner.

### [0:25–0:35] Step 2 — External CRO attempts same memo (DENY)

Click **Step 2**.

> "Owen Brooks, External CRO. Same artifact. No capability grant. DENY — `missing_capability_grant`. No clinical content returned."

Red `deny` banner. Empty content panel.

> **Key point:** Deterministic check on artifact ID — not LLM sensitivity filtering.

### [0:35–0:45] Step 3 — Inspect lineage

Click **Step 3**.

> "Four parents feed the derived memo: public target paper, internal SAR table, toxicity report, and adverse-event memo. Lineage is checked on every read — not just at derivation time."

Point to **Lineage** panel.

### [0:45–1:00] Step 4 — Revoke Adverse Event Memo

Click **Step 4**.

> "Data integrity issue on the adverse-event source. CEO revokes it. Watch quarantine cascade to derived artifacts — including the Phase II memo and any child derivations in the demo."

Amber `quarantined` badges. Status message with quarantined IDs.

### [1:00–1:10] Step 5 — Phase II memo quarantined

Click **Step 5**.

> "Phase II readiness memo and descendants now show quarantined status. Revoked adverse_event_memo sealed the derived lineage chain."

### [1:10–1:20] Step 6 — CEO denied on Phase II memo

Click **Step 6**.

> "CEO — who was allowed earlier — is now DENY. `derived_from_revoked_source`. Lineage sealed the derived memo when the source was revoked. No plaintext returned."

### [1:20–1:40] Step 7 — Audit log

Click **Step 7**. Scroll to **Audit Log**. Expand a row.

> "Every decision logged: `request_id`, principal, artifact, operation, decision, reason, purpose, latency_ms. Click any row for structured provenance."

### [1:40–2:00] Step 8 — Permission path evidence

Click **Step 8**. Point to **Compliance Matrix** and **Permission Latency**.

> "Pure SQL permission check — 0 model tokens, no LLM permission decision. P99 under 200 ms. Optional open-weight model only runs after authorization via POST /query."

---

## 30-second fallback

> "BioVault secures AI science memory in three ways: **One** — access is per artifact and token, not job title — CRO denied, Regulatory allowed. **Two** — lineage: revoke adverse-event data, Phase II memo quarantines automatically. **Three** — zero model tokens in the permission path — pure SQL, auditable, any agent calls POST /query before generation."

---

## Common judge questions

**Q: How is this different from document ACLs?**  
A: ACLs are flat. BioVault checks lineage dynamically — revoke a source, all derived descendants quarantine via BFS.

**Q: LLM sensitivity filtering?**  
A: That puts a model in the security path — token-heavy, jailbreakable. BioVault's permission path is SQL only.

**Q: Bypass token check?**  
A: No `?user_id=` override. `resolve_principal()` on every protected route. Test: `test_user_id_query_param_is_not_authority`.

**Q: Open-weight model integration?**  
A: `POST /query` is the agent gate — call before generation. No model imported in backend today; integration is the hook, not yet wired in this MVP.

**Q: Performance?**  
A: Indexed lineage traversal. P99 under 200ms in tests (`test_permission_latency_p99_under_200ms`).

**Q: Does it generalise to other domains?**  
A: The engine is domain-agnostic — capabilities, lineage, revocation, audit. BioVault's product focus is AI science / biotech R&D memory.
