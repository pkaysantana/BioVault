# BioVault Deployment Guide

Recommended path for a shareable hackathon demo:

| Layer | Platform | Why |
|---|---|---|
| **Frontend** | [Vercel](https://vercel.com) | Static Vite build, fast CDN, simple env vars |
| **Backend** | [Render](https://render.com) | Long-running FastAPI + SQLite demo; no serverless rewrite |

This repo keeps the permission engine on a normal web service to reduce hackathon risk. SQLite persistence is demo-only and resets on Render redeploys — users seed data from the UI.

---

## Prerequisites

- GitHub repo connected to Render and Vercel
- Backend deployed first (you need its public URL for the frontend env var)

---

## 1. Backend on Render

### Option A — Blueprint (`render.yaml`)

1. In Render: **New → Blueprint** → connect this repository.
2. Render reads [`render.yaml`](../render.yaml) at the repo root:
   - **Root directory:** `backend`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check:** `/health`
3. After the service is created, open **Environment** and set:

   | Variable | Example | Notes |
   |---|---|---|
   | `CORS_ALLOWED_ORIGINS` | `https://your-app.vercel.app,http://localhost:5173` | Comma-separated; include Vercel URL **and** localhost if you still develop locally against this API |
   | `DEMO_ALLOW_ALL_CORS` | `false` | Leave `false` unless you need a throwaway open demo |

4. Copy the service URL, e.g. `https://biovault-api.onrender.com`.

### Option B — Manual web service

1. **New → Web Service** → connect repo.
2. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. Add the same environment variables as above.

### Demo data

There is no automatic seed on boot. After opening the deployed frontend, click **Seed / Reset Demo** once. That calls `POST /seed` and loads principals, artifacts, and capability grants.

### SQLite note

`biovault.db` lives on Render’s ephemeral filesystem. Data survives restarts but may be lost on redeploy. Do not commit `backend/biovault.db` (it is gitignored).

---

## 2. Frontend on Vercel

1. **New Project** → import this repository.
2. **Root Directory:** `frontend`
3. **Framework Preset:** Vite (auto-detected)
4. **Build Command:** `npm run build`
5. **Output Directory:** `dist`
6. **Environment variable** (Production + Preview):

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://biovault-api.onrender.com` (your Render URL, no trailing slash) |

7. Deploy.

[`frontend/vercel.json`](../frontend/vercel.json) configures SPA fallback rewrites to `index.html` for client-side routing.

Local reference: [`frontend/.env.example`](../frontend/.env.example).

---

## 3. Environment variables summary

### Frontend (Vercel / local)

| Variable | Local default | Production |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Render backend URL |

### Backend (Render / local)

| Variable | Local default | Production |
|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `localhost:5173`, `localhost:3000` (+ 127.0.0.1) | Vercel URL + optional localhost |
| `DEMO_ALLOW_ALL_CORS` | unset / `false` | `false` |
| `BIOVAULT_DB` | `backend/biovault.db` | optional override |

Reference: [`backend/.env.example`](../backend/.env.example).

**Do not commit secrets.** Demo tokens are minted at seed time and returned in the HTTP response — acceptable for hackathon demo only.

---

## 4. Local verification

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass (includes audit evidence and latency checks).

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Optional: copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE_URL=http://localhost:8000`.

```powershell
cd frontend
npm run build
```

---

## 5. Post-deploy smoke test

1. Open the Vercel frontend URL.
2. Click **Seed / Reset Demo** — wait for “Demo seeded…” message.
3. **Step 1:** CEO opens Phase II Readiness Memo → **ALLOW**.
4. **Step 2:** External CRO opens same memo → **DENY** (`missing_capability_grant`).
5. **Step 4:** Revoke Adverse Event Memo → quarantine cascades.
6. Scroll to **Audit Log** → click a row → full `request_id` and structured detail visible.

Quick API check:

```bash
curl https://YOUR-RENDER-URL/health
# {"status":"ok","service":"biovault"}
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Frontend cannot reach backend | Wrong `VITE_API_BASE_URL` | Set to Render URL in Vercel env; redeploy frontend (Vite bakes env at build time) |
| Browser CORS error | Backend does not allow Vercel origin | Add `https://your-app.vercel.app` to `CORS_ALLOWED_ORIGINS` on Render; save and wait for restart |
| Empty users/artifacts | No seed yet | Click **Seed / Reset Demo** on the frontend |
| First request very slow | Render free tier cold start | Wait ~30s, refresh, try again |
| 401 on artifact reads | Seed not run or stale tab | Re-seed demo; ensure bearer tokens from seed are in client state |
| Data gone after redeploy | Ephemeral SQLite on Render | Re-seed demo — expected for hackathon demo |

---

## 7. Optional: Vercel-only backend (not recommended)

Vercel can host Python via [serverless functions](https://vercel.com/docs/functions/runtimes/python), but this repo **does not** ship a Vercel FastAPI adapter because:

- SQLite + serverless cold starts are awkward for a stateful demo.
- Render gives one long-lived process that matches local `uvicorn` behavior.
- Splitting frontend and backend across two platforms is already low-risk for judges.

If you experiment with Vercel functions, keep it in a separate branch and do not replace the Render service unless you accept demo persistence trade-offs.

---

## Security reminder

This deployment path is for **hackathon / judge demo** use. Capability-token auth, grant authority, redaction, lineage, and revocation logic are unchanged — but hardcoded Fernet keys, plaintext seed tokens, and SQLite are not production-ready. See [README.md](../README.md) residual limitations.
