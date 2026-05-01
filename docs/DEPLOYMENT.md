# Deployment Guide

This guide covers every deployment target for AURA v1: local Docker Compose, manual development setup, Vercel (frontend + serverless backend), and Render (traditional backend).

---

## Contents

- [Prerequisites](#prerequisites)
- [Local: Docker Compose](#local-docker-compose)
- [Local: Manual Setup](#local-manual-setup)
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

---

## Local: Docker Compose

This is the recommended path for local development and review.

```bash
git clone https://github.com/<your-org>/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
cp .env.example .env          # adjust if needed
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
    build: ./backend           # python:3.11-slim image
    port: 8000
    healthcheck: GET /health every 30s
    env: ENVIRONMENT, ALLOWED_ORIGINS, LOG_LEVEL

  frontend:
    build: ./frontend          # node:20-alpine multi-stage
    port: 3000
    depends_on: backend (service_healthy)
    env:
      NEXT_PUBLIC_API_URL: http://localhost:8000   # browser-facing
      API_URL: http://backend:8000                 # server-side / Docker internal
```

### Stopping and cleaning up

```bash
docker-compose down           # stop containers, preserve volumes
docker-compose down -v        # also remove volumes
docker-compose down --rmi all # also remove built images
```

---

## Local: Manual Setup

Use this when you want faster hot-reload for active development.

### 1 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start with auto-reload
uvicorn app.main:app --reload --port 8000
```

Environment variables can be exported in the shell or via a `.env` file (loaded by Pydantic Settings if configured).

```bash
export ALLOWED_ORIGINS="http://localhost:3000"
export LOG_LEVEL="DEBUG"
```

### 2 — Frontend

```bash
cd frontend
npm install

# Create .env.local for frontend-specific overrides
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev     # starts on http://localhost:3000 with hot reload
```

### 3 — Run tests

```bash
cd backend
pytest tests/ -v
```

### 4 — Retrain the model (optional)

Pre-built artifacts are included in `backend/model/`. To retrain from source data:

```bash
cd training
pip install -r requirements.txt
python preprocess.py       # → training/data/{train,val,test}.csv
python train.py            # → training/output/antibiotic_model.pkl
python evaluate.py         # → training/output/evaluation_report.json

# Copy new artifacts to backend
cp training/output/antibiotic_model.pkl  backend/model/
cp training/output/model_metadata.json   backend/model/
```

---

## Production: Vercel (Frontend)

The frontend is deployed via Vercel with the config in `vercel.json` at the repo root.

### Initial setup

1. Create a new Vercel project pointing to this repository.
2. Set the root directory to `.` (repository root).
3. Vercel reads `vercel.json` automatically.

**`vercel.json` key settings:**

```json
{
  "framework": "nextjs",
  "installCommand": "npm install --prefix frontend",
  "buildCommand":   "npm run build --prefix frontend",
  "outputDirectory": "frontend/.next"
}
```

### Environment variables (Vercel dashboard)

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-backend.onrender.com` (or your Render URL) |

Set this in **Vercel → Project → Settings → Environment Variables** for Production (and Preview if needed).

### Deploy

Every push to `main` triggers an automatic Vercel deployment. For manual deploys:

```bash
npm install -g vercel
vercel --prod
```

---

## Production: Render (Backend)

The backend is configured for Render's free-tier web service via `render.yaml`.

### Initial setup

1. Connect your GitHub repository to Render.
2. Render detects `render.yaml` and auto-creates the service.

**`render.yaml` key settings:**

```yaml
services:
  - type: web
    name: aura-cdss-backend
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.9
      - key: ALLOWED_ORIGINS
        value: https://your-frontend.vercel.app
```

### Environment variables (Render dashboard)

Set in **Render → Service → Environment** or via `render.yaml` `envVars`:

| Variable | Value |
|---|---|
| `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` |
| `LOG_LEVEL` | `INFO` |
| `ENVIRONMENT` | `production` |

### Model artifacts on Render

Render free-tier does not have persistent disk. The model artifacts (`backend/model/`) must be committed to the repository or loaded from an external storage location at startup.

The current setup commits the model pickle to the repo. For large models, consider:
- Git LFS
- Downloading from S3/GCS at startup (add to `startCommand` or a startup script)

### Deploy

Every push to `main` triggers a Render auto-deploy if the service is connected to the branch. Manual deploy via the Render dashboard or CLI:

```bash
render deploy --service-id <service-id>
```

---

## Production: Vercel (Serverless Backend)

An alternative backend deployment that runs FastAPI as a Vercel serverless function.

**Files involved:**
- `backend/vercel.json` — routes all requests to `api/index.py`
- `backend/api/index.py` — imports and re-exports the FastAPI `app`

### Setup

1. Create a separate Vercel project pointing to the `backend/` subdirectory.
2. Vercel reads `backend/vercel.json`.
3. Set environment variables in the Vercel dashboard.

**Limitations of serverless:**
- Cold starts (100–500ms) on the first request.
- Execution timeout (Vercel free tier: 10 seconds). Long model inference may time out.
- No persistent disk — model must be bundled into the deployment package or fetched from storage.
- The free tier has a 50 MB compressed deployment size limit. The model pickle may exceed this.

**Recommendation:** Use Render for the backend; reserve serverless for lightweight APIs.

---

## Environment Variables Reference

Full list with defaults:

| Variable | Default | Required in prod | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | No | Startup log label |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | **Yes** | CORS allowlist (comma-separated) |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity |
| `PORT` | `8000` | No (Render injects) | Uvicorn port |
| `MODEL_PATH` | `model/antibiotic_model.pkl` | No | Relative to working dir |
| `MODEL_METADATA_PATH` | `model/model_metadata.json` | No | Relative to working dir |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | **Yes** | Browser API base URL |
| `API_URL` | `http://backend:8000` | No (Docker only) | Server-side API URL |

---

## Health Checks

### Backend

```
GET /health
→ 200 { "status": "healthy", "service": "antibiotic-ai-cdss" }
```

Used by:
- Docker Compose (`healthcheck`)
- Render (`healthCheckPath`)
- Load balancers / uptime monitors

### Frontend

Next.js does not expose a dedicated health endpoint. Monitor the root page (`/`) or use Vercel's built-in uptime monitoring.

---

## Troubleshooting

### Backend starts but model is not loaded

Symptom: `/api/v1/antibiotics` returns an empty list; `/health` still returns 200.

Cause: `MODEL_PATH` points to a file that does not exist. The service starts in fallback mode.

Fix:
```bash
ls -lh backend/model/         # verify antibiotic_model.pkl exists
# If missing, retrain or restore from the training/output/ copies:
cp training/output/antibiotic_model.pkl backend/model/
cp training/output/model_metadata.json  backend/model/
```

### Frontend cannot reach backend

Symptom: `Network Error` or `CORS error` in browser console.

Checks:
1. `NEXT_PUBLIC_API_URL` must match the backend URL exactly (scheme, host, port, no trailing slash).
2. `ALLOWED_ORIGINS` on the backend must include the frontend's origin.
3. In Docker Compose: the frontend container uses `API_URL=http://backend:8000` (internal) but the browser needs `NEXT_PUBLIC_API_URL=http://localhost:8000` (external).

### Docker Compose: frontend exits immediately

Cause: `depends_on: backend: condition: service_healthy` — the frontend waits for the backend healthcheck to pass. If the backend fails its healthcheck (model not loading, port conflict), the frontend will not start.

```bash
docker-compose logs backend   # check for startup errors
docker-compose ps             # check service health status
```

### Render: 502 Bad Gateway

Cause: Uvicorn failed to bind or crashed at startup.

```bash
# Check Render logs in the dashboard
# Common causes:
# 1. PORT variable not passed to uvicorn (render.yaml uses $PORT — this is correct)
# 2. requirements.txt install failed (check build logs)
# 3. Model pickle missing or corrupted
```

### Vercel build fails: output directory not found

Cause: `outputDirectory: frontend/.next` — the build must run inside the `frontend/` directory.

Fix: Verify `buildCommand` is `npm run build --prefix frontend` and that `frontend/next.config.js` exists.
