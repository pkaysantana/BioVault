# BioVault — Demo Scripts

---

## 2-minute demo (judge walkthrough)

**Setup** (done before the demo starts)

- Backend running: `uvicorn app.main:app --reload` on port 8000
- Frontend running: `npm run dev` on port 5173
- Browser open at `http://localhost:5173`

---

### Intro (10 s)

> "BioVault is a capability-secured artifact memory layer for AI science agents. The core idea: access to an artifact is governed by a cryptographic capability token, not a user role. When a source artifact is revoked, BioVault automatically quarantines every derived artifact downstream — without asking any model. I'll show you that in six steps."

---

### Step 1 — CEO opens Phase II memo (15 s)

1. Click **Step 1: CEO reads Phase II memo**.
2. Point to the artifact panel: content is decrypted and shown.
3. Point to the decision badge: `ALLOW — capability_and_lineage_valid`.

> "Avery Chen, our CEO, holds a capability grant for `read` on this exact artifact. All four source artifacts the memo was derived from are active and healthy. Access allowed."

---

### Step 2 — External CRO denied (15 s)

1. Click **Step 2: External CRO attempts Phase II memo**.
2. The artifact panel shows no content.
3. Decision badge: `DENY — missing_capability_grant`.

> "Owen Brooks, the external CRO, has no capability grant for this artifact. Not because of his role — because there is no grant record in the capability table. BioVault never checked his job title."

---

### Step 3 — Regulatory Lead allowed (15 s)

1. Click **Step 3: Regulatory Lead reads Phase II memo**.
2. Content shown, `ALLOW`.

> "Nora Singh has an explicit grant. Same artifact, same token-bound check, different outcome. This is artifact-level access, not role-level access."

---

### Step 4 — Revoke Adverse Event Memo (20 s)

1. Click **Step 4: Revoke Adverse Event Memo**.
2. Watch the status toast: "adverse_event_memo revoked. Quarantined: phase2_readiness_memo, exec_brief_… (2 artifacts)."
3. Point to the artifact list: both downstream artifacts now show amber `quarantined` badges.

> "The backend derived a child 'Exec Brief' from Phase II first, then revoked the adverse-event source memo. BioVault ran a BFS over the lineage graph and quarantined every active descendant — Phase II memo and the Exec Brief — in one synchronous pass."

---

### Step 5 — Show quarantine state (15 s)

1. Click **Step 5: Inspect quarantined artifacts**.
2. Decision badge: `DENY — derived_from_revoked_source`, even for the CEO who previously had access.

> "The CEO had access 30 seconds ago. The source is now revoked, so the derived artifact is quarantined. No capability grant can override a quarantine — the lineage check runs after the grant check."

---

### Step 6 — Audit log & latency (15 s)

1. Click **Step 6: Audit log & latency evidence**.
2. Point to the Compliance Matrix: nine rows, all PASS. The P99 row shows a live millisecond reading.
3. Scroll to the audit table: every decision has a `request_id`, `reason`, and latency.

> "Every access attempt is logged — allow or deny. The P99 latency for the permission check is under 200 milliseconds on SQLite with no warm-up. The compliance matrix maps directly to the BasedAI track requirements."

---

### Close (5 s)

> "BioVault demonstrates that artifact-level governance can be deterministic, auditable, and fast — with no model in the permission path. The permission gate runs before any open-weight model ever sees the content."

---

## 30-second fallback demo

Use this if only the frontend is visible or the demo needs to be cut short.

---

**Open the frontend at `http://localhost:5173`.**

> "BioVault secures AI-generated artifacts by capability token, not by role. Watch:"

1. Click **Step 1** — CEO gets access.
2. Click **Step 2** — CRO is denied. Same artifact, different token, no grant.
3. Click **Step 4** — Revoke the source. Two downstream artifacts are instantly quarantined.
4. Point to the Compliance Matrix: "Nine requirements, nine PASSes. P99 latency is live. No model in the permission path."

> "Deterministic, lineage-aware, auditable. That's BioVault."
