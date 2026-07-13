# Deployment Guide

Deployment targets for AURA **V2** (`version/v2_release`): local Docker Compose, manual development setup, Vercel (frontend), and Render (backend). The trained V2 artifacts are **committed** to `armd_model/artifacts/`, so the app runs **without retraining**.

> **Branch note:** this branch serves only `/api/v2/*`. V1 (CatBoost) deploys separately from `main`.

---

## Contents

- [Prerequisites](#prerequisites)
- [Local: Docker Compose](#local-docker-compose)
- [Local: Manual Setup](#local-manual-setup)
- [Retraining the V2 models](#retraining-the-v2-models)
- [Production: Vercel (Frontend)](#production-vercel-frontend)
- [Production: Render (Backend)](#production-render-backend)
- [Production: Vercel (Serverless Backend)](#production-vercel-serverless-backend)
- [Environment Variables Reference](#environment-variables-reference)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Docker | 24+ | Container runtime |
| Docker Compose | v2+ | Multi-container orchestration |
| Python | 3.11+ | Backend and training |
| Node.js | 20+ | Frontend build |
| npm | 10+ | Frontend dependencies |

> **Critical pin:** the backend requires **`scikit-learn==1.3.2`** (in `backend/requirements.txt`). The committed model artifacts were pickled with 1.3.2 and a newer sklearn fails to unpickle them (`SimpleImputer has no attribute _fill_dtype`), causing `/api/v2/recommend` to 500. Train with the same version.

---

## Local: Docker Compose

Recommended for local runs and review. No retraining needed — artifacts are committed.

```bash
git clone https://github.com/EponymousBearer/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
git checkout version/v2_release
cp .env.example .env
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

### What the Compose file does

```yaml
services:
  backend:
    build: ./backend           # backend/Dockerfile
    port: 8000
    healthcheck: GET /health
    env: ENVIRONMENT, ALLOWED_ORIGINS
    # armd_model/artifacts/ ships in the build context and loads at startup

  frontend:
    build: ./frontend
    port: 3000
    depends_on: backend (service_healthy)
    env:
      NEXT_PUBLIC_API_URL: http://localhost:8000   # browser-facing
      API_URL: http://backend:8000                 # internal Docker network
```

### Stopping

```bash
docker-compose down            # stop containers
docker-compose down --rmi all  # also remove built images
```

---

## Local: Manual Setup

### 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # installs scikit-learn==1.3.2
uvicorn app.main:app --reload --port 8000
```

```bash
export ALLOWED_ORIGINS="http://localhost:3000"
# optional overrides:
export ARMD_ARTIFACTS_DIR="../armd_model/artifacts"
export ARMD_COHORT_PATH="../datasets/microbiology_cultures_cohort.csv"
```

### 2 — Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

### 3 — Tests

```bash
cd backend && pytest tests/ -v
```

---

## Retraining the V2 models

Only needed if you replace the datasets or change the model config. Place the ARMD CSVs in `datasets/` (see the [Google Drive link](https://drive.google.com/drive/folders/1agc1hXlVinXAPM-7E8RFfAFopKVrIota?usp=sharing)), then run the **three** scripts in order with `scikit-learn==1.3.2`:

```bash
cd armd_model
pip install -r requirements.txt        # pin scikit-learn==1.3.2 to match the backend

python train_armd.py          # RF recommender → rf_top3_recommender_optimized.joblib (+ metadata, threshold, summary, importances)
python build_antibiogram.py   # antibiogram filter → organism_antibiotic_panel.json
python train_dosage.py        # dosage → dose_route_lookup.csv + dose/route_model_hybrid.pkl
```

Restart the backend afterward — artifacts load once at startup.

---

## Production: Vercel (Frontend)

The frontend deploys to Vercel with **Root Directory = `frontend`**. There is **no root `vercel.json`** (it was removed to fix a build/404 conflict).

### Setup

1. Create a Vercel project pointing at this repo.
2. **Settings → General → Root Directory → `frontend`.**
3. Framework preset: Next.js (auto-detected).

### Environment variables (Vercel dashboard)

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<your-render-backend>.onrender.com` |

### Deploy

Pushes to the connected branch trigger automatic deploys. Manual: `vercel --prod` (run from `frontend/` or with the root directory configured).

---

## Production: Render (Backend)

The backend deploys to Render's free tier **from `backend/Dockerfile`**. There is **no `render.yaml`** (removed to fix a conflicting config).

### Setup

1. New → Web Service → connect this repo.
2. Runtime: **Docker**; Dockerfile path `backend/Dockerfile`; root directory `backend` (or repo root with the Dockerfile path set).
3. Health check path: `/health`.

### Environment variables (Render dashboard)

| Variable | Value |
|---|---|
| `ALLOWED_ORIGINS` | `https://<your-frontend>.vercel.app` |
| `ENVIRONMENT` | `production` |
| `ARMD_ARTIFACTS_DIR` | *(optional)* defaults to the in-image `armd_model/artifacts` |
| `ANTIBIOGRAM_DIR` | *(optional)* defaults to the in-image `/app/antibiograms` |
| `REPORTS_DIR` | *(optional)* defaults to `/app/reports` (set in the Dockerfile) |

### Model artifacts on Render

Render's free tier has no persistent disk. The V2 artifacts are **committed to the repo** and bundled into the image — sized (150 trees / depth 16 / `compress=3`) to fit the 512 MB free-tier RAM and GitHub's 100 MB file limit. No external storage needed. The bundled set is:

- **`rf_top3_recommender_calibrated.joblib`** — the **served** recommender (isotonic-calibrated, M1); `armd_predictor` prefers it over the raw RF.
- `organism_antibiotic_panel.json`, `dose_route_lookup.csv`, and the small `*.joblib`/`*.json` metadata.
- **`backend/antibiograms/*.json`** (M4) — the per-locale antibiograms driving the Pakistan/Route-A path and the US-vs-PK contrast. Copied to `/app/antibiograms`.
- **`reports/metrics.json`** (M1) — read by `/api/v2/model-info` to populate the evaluation dashboard. The figures themselves ship with the **frontend** (`frontend/public/figures/`).

The large retired dose/route ML `.pkl`s (>100 MB) are **not** shipped — M5 retired ML dosing, so the dosage service uses the lookup + static table only.

---

## Production: Vercel (Serverless Backend)

An alternative that runs FastAPI as a Vercel function via `backend/vercel.json` → `backend/api/index.py`.

**Limitations:** cold starts; execution timeout (free tier ~10 s); 50 MB compressed deployment limit (the RF artifact may exceed this); no persistent disk. **Recommendation:** use Render for the backend; reserve serverless for lightweight APIs.

---

## Environment Variables Reference

| Variable | Default | Required in prod | Used by | Description |
|---|---|---|---|---|
| `ENVIRONMENT` | `development` | No | Backend | Startup log label |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | **Yes** | Backend | CORS allowlist (comma-separated) |
| `ARMD_ARTIFACTS_DIR` | `<repo>/armd_model/artifacts` | No | Backend (V2) | RF + dosage lookup artifacts |
| `ANTIBIOGRAM_DIR` | `<repo>/backend/antibiograms` | No | Backend (V2) | Per-locale antibiograms (M4) — Pakistan path + contrast |
| `REPORTS_DIR` | `/app/reports` (Docker) | No | Backend (V2) | `metrics.json` for the `/model-info` evaluation block |
| `ARMD_COHORT_PATH` | `<repo>/datasets/microbiology_cultures_cohort.csv` | No | Backend (V2) | Runtime organism catalog source |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | **Yes** | Frontend | Browser API base URL |
| `API_URL` | `http://backend:8000` | No (Docker only) | Frontend | Server-side API URL |

> `MODEL_PATH` / `MODEL_METADATA_PATH` are V1-only (CatBoost) and not used on this branch.

---

## Health Checks

```
GET /health → 200 { "status": "healthy", "service": "antibiotic-ai-cdss" }
```

Used by Docker Compose, Render (`healthCheckPath`), and uptime monitors. The frontend has no dedicated health endpoint — monitor `/`.

---

## Troubleshooting

### `/api/v2/recommend` returns 503

The ARMD model didn't load. Verify the artifacts exist and `ARMD_ARTIFACTS_DIR` points to them:

```bash
ls armd_model/artifacts/
# Expected: rf_top3_recommender_optimized.joblib, feature_cols.joblib,
#           organism_antibiotic_panel.json, dose_route_lookup.csv, ...
```

If missing, retrain (see [above](#retraining-the-v2-models)).

### `/api/v2/recommend` returns 500 with `_fill_dtype`

scikit-learn version mismatch. The backend env must be on **`scikit-learn==1.3.2`** to unpickle the committed artifacts. Reinstall: `pip install -r backend/requirements.txt`.

### `/api/v2/recommend` returns 422

Unsupported culture site, or the organism isn't valid for the chosen site. Call `GET /api/v2/organisms?culture_description=<site>` for valid options (or use `other`).

### Frontend cannot reach backend

1. `NEXT_PUBLIC_API_URL` must match the backend URL exactly (scheme, host, port, no trailing slash).
2. `ALLOWED_ORIGINS` on the backend must include the frontend origin.
3. In Docker: the browser uses `NEXT_PUBLIC_API_URL=http://localhost:8000` while the frontend container uses `API_URL=http://backend:8000`.

### Organism dropdown is sparse

`ClinicalCatalogService` couldn't read the cohort CSV, so it fell back to a small built-in list. Provide `datasets/microbiology_cultures_cohort.csv` or set `ARMD_COHORT_PATH`.

### Vercel build fails / 404

Ensure **Root Directory = `frontend`** and that there is no stray root `vercel.json`.
