# Build Status

Current state of every feature across V1 and V2, local setup checklist, and pending work tracker.

**Legend:** ✅ Complete · 🔧 Requires action · ⏳ Pending / planned · ❌ Not implemented

---

## Contents

- [V1 Feature Status](#v1-feature-status)
- [V2 Feature Status](#v2-feature-status)
- [Local Setup Checklist](#local-setup-checklist)
- [File Inventory](#file-inventory)
- [Known Issues](#known-issues)
- [Pending Work](#pending-work)

---

## V1 Feature Status

V1 uses the Dryad microbiology dataset with CatBoost binary classifiers (one per antibiotic).

### Backend

| Feature | Status | Notes |
|---|---|---|
| FastAPI application + middleware | ✅ | `backend/app/main.py` |
| CORS configuration | ✅ | Controlled by `ALLOWED_ORIGINS` env var |
| Request logging + timing middleware | ✅ | All requests logged with duration |
| `X-Request-ID` tracing header | ✅ | UUID propagated through every response |
| Global exception handler | ✅ | Environment-aware detail disclosure |
| `GET /` — API info | ✅ | Returns version and endpoint map |
| `GET /health` — liveness probe | ✅ | Used by Docker, Render, load balancers |
| `GET /api/v1/organisms` | ✅ | 14 supported organisms enumerated |
| `GET /api/v1/antibiotics` | ✅ | Derived from loaded model |
| `POST /api/v1/recommend` | ✅ | CatBoost prediction + rule dosing |
| `POST /api/v1/explain` | ✅ | SHAP feature importance |
| `GET /api/v1/explain` | ✅ | Same via query string |
| `GET /api/v1/model-info` | ✅ | Per-antibiotic AUC/F1/accuracy |
| CatBoost prediction service | ✅ | `backend/app/services/predictor.py` |
| Baseline-correction ranking | ✅ | Subtracts training positive rate |
| Organism compatibility weighting | ✅ | 0.25 penalty for intrinsically inactive agents |
| Rule-based dosing engine | ✅ | 20+ antibiotics, 4-tier renal adjustment |
| Fallback mode (no model file) | ✅ | Hardcoded susceptibility patterns |
| Pydantic v2 validation schemas | ✅ | `backend/app/schemas/request.py` |

### V1 Model Artifacts

| Artifact | Status | Path |
|---|---|---|
| `antibiotic_model.pkl` | ✅ Present | `backend/model/` |
| `model_metadata.json` | ✅ Present | `backend/model/` |
| Training data (Dryad CSVs) | ✅ Present | `training/` |
| Preprocessed splits | ✅ Present | `training/data/` |
| Training script | ✅ | `training/train.py` |
| Evaluation script | ✅ | `training/evaluate.py` |

### Frontend (V1)

| Feature | Status | Notes |
|---|---|---|
| V1 `PatientForm` | ✅ | `ResultCard.tsx` still uses v1 SHAP explain |
| `ResultCard` with SHAP modal | ✅ | `components/ResultCard.tsx` |
| `ResistanceChart` | ✅ | All antibiotics ranked by probability |
| `DisclaimerBanner` | ✅ | Reusable warning/info component |
| `/model-info` page | ✅ | V2 model inventory, held-out test results, feature importances, dosage status |
| Retry on error | ✅ | Stores last request, re-submits |

---

## V2 Feature Status

V2 uses the ARMD dataset with a single RandomForest pipeline across 32 antibiotics.

### Backend

| Feature | Status | Notes |
|---|---|---|
| `POST /api/v2/recommend` | ✅ | Full pipeline: ARMD prediction + dosage |
| `GET /api/v2/model-info` | ✅ | RF model status, test summary, feature importances, dosage model metadata |
| `ARMDPredictorService` | ✅ | `backend/app/services/armd_predictor.py` |
| `DosageService` | ✅ | `backend/app/services/dosage_service.py` |
| Ward → binary flag mapping | ✅ | general/icu/er → ward__ip/icu/er |
| Lab value passthrough | ✅ | wbc/cr/lactate/procalcitonin → model features |
| Hybrid dosage (lookup → ML → rules) | ✅ | 3-tier fallback chain |
| 503 when model not trained | ✅ | Clear error message with fix instructions |
| V2 Pydantic schemas | ✅ | `ARMDRecommendationRequest`, `ARMDResult` |

### V2 Model Artifacts

| Artifact | Status | Path |
|---|---|---|
| `rf_top3_recommender_optimized.joblib` | ✅ Present | `armd_model/artifacts/` |
| `feature_cols.joblib` | ✅ Present | `armd_model/artifacts/` |
| `selected_antibiotics.joblib` | ✅ Present | `armd_model/artifacts/` |
| `best_threshold.joblib` | ✅ Present | `armd_model/artifacts/` |
| `split_test_summary.joblib` | ✅ Present | `armd_model/artifacts/` |
| `feature_importances.joblib` | ✅ Present | `armd_model/artifacts/` |
| `metadata_optimized.json` | ✅ Present | `armd_model/artifacts/` |
| `dose_route_lookup.csv` | ✅ Present | `armd_model/artifacts/` |
| `dose_model_hybrid.pkl` | ✅ Present | `armd_model/artifacts/` |
| `route_model_hybrid.pkl` | ✅ Present | `armd_model/artifacts/` |

**To generate:** run `armd_model/train_armd.py` then `armd_model/train_dosage.py`

### V2 Dataset Files

| File | Status | Used by |
|---|---|---|
| `microbiology_cultures_cohort.csv` | ✅ Present in `datasets/` | `train_armd.py` (core) |
| `microbiology_cultures_demographics.csv` | ✅ Present in `datasets/` | `train_armd.py` |
| `microbiology_cultures_labs.csv` | ✅ Present in `datasets/` | `train_armd.py` |
| `microbiology_cultures_antibiotic_class_exposure.csv` | ✅ Present in `datasets/` | `train_armd.py` |
| `microbiology_culture_prior_infecting_organism.csv` | ✅ Present in `datasets/` | `train_armd.py` |
| `microbiology_cultures_ward_info.csv` | ✅ Present in `datasets/` | `train_armd.py` (optional) |
| `d_dose.csv` | ✅ Present in `datasets/` | `train_dosage.py` |

### Frontend (V2)

| Feature | Status | Notes |
|---|---|---|
| V2 `PatientForm` | ✅ | `components/PatientForm.tsx` — culture, organism, age, gender, labs, ward |
| `ResultCardV2` | ✅ | `components/ResultCardV2.tsx` — probability bar + dose range + route |
| V2 main page | ✅ | `app/page.tsx` — wired to `/api/v2/recommend` |
| Full resistance chart | ✅ | Shared `ResistanceChart` component |
| 503 error message with fix instructions | ✅ | Shows training command |
| Retry on error | ✅ | |
| SHAP explainability per recommendation | ⏳ | RF model has global importances; per-prediction SHAP needs TreeSHAP integration |
| Prior history inputs in form | ⏳ | `prior_abxclass__*` / `prior_org__*` default to 0 at inference |

---

## Local Setup Checklist

Follow these steps in order for a fully working local environment.

### Prerequisites

- [ ] Python 3.11+ installed (`python --version`)
- [ ] Node.js 20+ installed (`node --version`)
- [ ] npm 10+ installed (`npm --version`)
- [ ] Git installed

### Step 1 — Clone and configure

```bash
git clone https://github.com/EponymousBearer/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
cp .env.example .env
```

- [ ] `.env` file created

### Step 2 — Install backend dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

- [ ] Virtual environment created
- [ ] All packages installed without errors

### Step 3 — Install frontend dependencies

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

- [ ] `node_modules/` created
- [ ] `.env.local` created

### Step 4 — Verify V1 artifacts are present

```bash
ls backend/model/
# Expected: antibiotic_model.pkl  model_metadata.json
```

- [ ] `antibiotic_model.pkl` exists
- [ ] `model_metadata.json` exists

If missing, retrain V1:
```bash
cd training && pip install -r requirements.txt
python preprocess.py && python train.py && python evaluate.py
cp training/output/antibiotic_model.pkl backend/model/
cp training/output/model_metadata.json  backend/model/
```

### Step 5 — Train V2 model (required for V2 features)

Confirm datasets are present:
```bash
ls datasets/
# Expected: 7 CSV files including d_dose.csv
```

```bash
cd armd_model
pip install -r requirements.txt
python train_armd.py          # ~5–20 min depending on dataset size
python train_dosage.py        # ~1–3 min
```

- [ ] `armd_model/artifacts/rf_top3_recommender_optimized.joblib` created
- [ ] `armd_model/artifacts/dose_route_lookup.csv` created

### Step 6 — Start services

Terminal 1 (backend):
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Terminal 2 (frontend):
```bash
cd frontend
npm run dev
```

### Step 7 — Verify

- [ ] `http://localhost:8000/health` → `{"status": "healthy"}`
- [ ] `http://localhost:8000/docs` → Swagger UI loads
- [ ] `http://localhost:3000` → Frontend loads
- [ ] Submit a V2 recommendation form → top 3 results displayed

### Docker alternative (V1 only)

```bash
docker-compose up --build
```

- [ ] Frontend accessible at `http://localhost:3000`
- [ ] Backend accessible at `http://localhost:8000`

> V2 requires model artifacts in `armd_model/artifacts/` which must be trained locally first, then the Docker image rebuilt.

---

## File Inventory

### New files added in V2

| File | Purpose |
|---|---|
| `armd_model/train_armd.py` | ARMD RF training script (adapted from Colab) |
| `armd_model/train_dosage.py` | Dosage model training script (adapted from Colab) |
| `armd_model/requirements.txt` | Training dependencies |
| `backend/app/services/armd_predictor.py` | V2 RF inference service |
| `backend/app/services/dosage_service.py` | V2 hybrid dosage service |
| `frontend/components/PatientForm.tsx` | V2 clinical input form (replaced v1) |
| `frontend/components/ResultCardV2.tsx` | V2 recommendation card |
| `datasets/.gitkeep` | Placeholder for datasets directory |

### Modified files in V2

| File | What changed |
|---|---|
| `backend/app/schemas/request.py` | Added `ARMDRecommendationRequest`, `ARMDResult`, `ARMDRecommendationResponse`, `WardEnum` |
| `backend/app/api/routes.py` | Added `v2_router` with `/recommend` and `/model-info` |
| `backend/app/main.py` | Registered `v2_router` at `/api/v2` |
| `backend/requirements.txt` | Added `joblib==1.3.2` |
| `frontend/types/index.ts` | Added `ARMDFormData`, `ARMDRecommendation`, `ARMDRecommendationResponse` |
| `frontend/services/api.ts` | Added `getARMDRecommendation()`, `getARMDModelInfo()` |
| `frontend/components/index.ts` | Added `ResultCardV2`, `ResistanceChart`, `DisclaimerBanner` exports |
| `frontend/app/page.tsx` | Rewired to V2 form, `ResultCardV2`, `/api/v2/recommend` |

### Documentation files (all new/updated)

| File | Status |
|---|---|
| `README.md` | ✅ Updated — V1 + V2, quick start, full layout, both APIs |
| `CHANGELOG.md` | ✅ Updated — V2.0.0 section added |
| `CONTRIBUTING.md` | ✅ Complete — branch conventions, code style, PR process |
| `SECURITY.md` | ✅ Complete — pickle policy, CORS, validation, disclosure |
| `LICENSE` | ✅ Complete — MIT + medical disclaimer |
| `.env.example` | ✅ Updated — all env vars including V2 |
| `docs/API_REFERENCE.md` | ✅ Updated — V1 + V2 endpoints |
| `docs/ARCHITECTURE.md` | ✅ Updated — V1 + V2 services, data flow |
| `docs/MODEL.md` | ✅ Updated — CatBoost V1 + ARMD RF V2 |
| `docs/DEPLOYMENT.md` | ✅ Updated — V2 training steps, new env vars |
| `docs/BUILD_STATUS.md` | ✅ This file |

---

## Known Issues

| Issue | Severity | Status | Workaround |
|---|---|---|---|
| V2 artifacts must be regenerated after dataset changes | Operational | ✅ Current artifacts present | Run `armd_model/train_armd.py` and `train_dosage.py` after replacing datasets |
| V2 SHAP per-prediction not available | Minor | ⏳ Planned | Use global feature importances from `feature_importances.joblib` |
| Prior history features default to 0 | Moderate | ⏳ Planned | All `prior_abxclass__*` and `prior_org__*` set to 0 at inference |
| Docker image does not include V2 artifacts | Minor | 🔧 Manual | Mount `armd_model/artifacts/` as a volume or rebuild after training |

---

## Pending Work

### High priority

- [x] **Train V2 model** — artifacts present in `armd_model/artifacts/`
- [ ] **Update Docker Compose** to mount `armd_model/artifacts/` into the backend container
- [ ] **Set `ARMD_ARTIFACTS_DIR`** in `.env` / production environment variables

### Medium priority

- [ ] Add per-prediction TreeSHAP explainability to V2 `ResultCardV2`
- [ ] Add prior antibiotic class / prior organism fields to V2 form (advanced section)
- [x] Fix pre-existing TypeScript issue in `model-info/page.tsx`
- [x] Add V2 model performance page (equivalent of `/model-info` for ARMD)
- [x] Write backend tests for V2 model-info route (`backend/tests/test_v2_api.py`)

### Low priority

- [ ] Calibrate V2 probabilities (isotonic regression post-processing)
- [ ] Add concept drift detection hook
- [ ] Update `docker-compose.yml` with `ARMD_ARTIFACTS_DIR` volume mount
- [ ] Add `manual_test_cases_unambiguous.csv` to `datasets/` for dosage evaluation
- [ ] External validation on an independent hospital dataset
- [ ] User authentication + audit logging
