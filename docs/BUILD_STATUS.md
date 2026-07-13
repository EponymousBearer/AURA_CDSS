# Build Status

State of every feature, local setup checklist, and pending work for AURA. This branch (`version/v2_release`) ships **V2 (ARMD RandomForest)** as the active system; **V1 (CatBoost)** is the separate `main`-branch product and is commented out here.

**Legend:** ✅ Complete · 🔧 Requires action · ⏳ Pending / planned · 🚫 Disabled on this branch

---

## Contents

- [V2 Feature Status (active)](#v2-feature-status-active)
- [V1 Feature Status (legacy, main)](#v1-feature-status-legacy-main)
- [Local Setup Checklist](#local-setup-checklist)
- [File Inventory](#file-inventory)
- [Known Issues](#known-issues)
- [Pending Work](#pending-work)

---

## V2 Feature Status (active)

V2 uses the ARMD dataset with a single RandomForest pipeline across 32 antibiotics, an antibiogram filter, and a hybrid dosage model.

### Backend

| Feature | Status | Notes |
|---|---|---|
| FastAPI app + CORS + logging/timing middleware + global handler | ✅ | `backend/app/main.py` (mounts only `/api/v2`) |
| `X-Request-ID` tracing | ✅ | UUID on every response incl. errors |
| `GET /` / `GET /health` | ✅ | Root points to `/api/v2/recommend` |
| `GET /api/v2/organisms` | ✅ | Culture-site → organism catalog from cohort CSV |
| `POST /api/v2/recommend` | ✅ | 3-layer engine + dosage enrichment |
| `GET /api/v2/model-info` | ✅ | RF status, test summary, importances, dosage status |
| `ARMDPredictorService` | ✅ | RF scoring + antibiogram filter + ranking |
| Antibiogram clinical filter | ✅ | `organism_antibiotic_panel.json`, CLSI M39 ≥30 isolates, 85 organisms |
| `ClinicalCatalogService` | ✅ | Validates culture site + organism (422 on invalid) |
| `DosageService` (lookup → ML → static) | ✅ | 3-tier; never returns "unknown" |
| Ward → binary flags | ✅ | general→ip, icu, er |
| Lab passthrough + imputation | ✅ | wbc/cr/lactate/procalcitonin |
| 503 when model not trained | ✅ | Clear message with training command |
| V2 Pydantic schemas | ✅ | `ARMDRecommendationRequest`, `ARMDResult`, `WardEnum` |
| `scikit-learn==1.3.2` pin | ✅ | Required to unpickle artifacts |

### V2 Model Artifacts (`armd_model/artifacts/`)

| Artifact | Status | Produced by |
|---|---|---|
| `rf_top3_recommender_optimized.joblib` | ✅ Present | `train_armd.py` |
| `feature_cols.joblib` | ✅ Present | `train_armd.py` |
| `selected_antibiotics.joblib` | ✅ Present | `train_armd.py` |
| `best_threshold.joblib` (0.5) | ✅ Present | `train_armd.py` |
| `split_test_summary.joblib` | ✅ Present | `train_armd.py` |
| `feature_importances.joblib` | ✅ Present | `train_armd.py` |
| `metadata_optimized.json` | ✅ Present | `train_armd.py` |
| `organism_antibiotic_panel.json` | ✅ Present | `build_antibiogram.py` |
| `dose_route_lookup.csv` (840 rows) | ✅ Present | `train_dosage.py` |
| `dose_model_hybrid.pkl` / `route_model_hybrid.pkl` | ✅ Present | `train_dosage.py` |

**To regenerate:** `train_armd.py` → `build_antibiogram.py` → `train_dosage.py` (all three, with sklearn 1.3.2).

### V2 Dataset Files (`datasets/`, not committed)

| File | Used by |
|---|---|
| `microbiology_cultures_cohort.csv` | `train_armd.py` (core) · `build_antibiogram.py` · runtime catalog |
| `microbiology_cultures_demographics.csv` | `train_armd.py` |
| `microbiology_cultures_labs.csv` | `train_armd.py` |
| `microbiology_cultures_antibiotic_class_exposure.csv` | `train_armd.py` |
| `microbiology_culture_prior_infecting_organism.csv` | `train_armd.py` |
| `microbiology_cultures_ward_info.csv` | `train_armd.py` |
| `d_dose.csv` | `train_dosage.py` |

### Frontend (V2)

| Feature | Status | Notes |
|---|---|---|
| `PatientForm` | ✅ | culture, organism, age, gender, ward, optional labs |
| `ResultCardV2` | ✅ | probability bar + dose range + route + source |
| Main page wired to `/api/v2/recommend` | ✅ | `app/page.tsx` |
| `ResistanceChart` | ✅ | all scored antibiotics, ranked |
| `/model-info` dashboard | ✅ | V2 inventory + test metrics + importances |
| 503 error message with fix instructions | ✅ | shows training command |
| Per-prediction SHAP | ⏳ | global importances only; TreeSHAP planned |
| Prior-history inputs in form | ⏳ | `prior_*` default to 0 at inference |

---

## V1 Feature Status (legacy, `main`)

The full CatBoost stack (23 per-antibiotic classifiers, rule-based dosing, SHAP, baseline-correction ranking) is **complete on `main`** and **disabled on this branch**.

| Area | Status on this branch |
|---|---|
| `/api/v1/*` routes | 🚫 Commented out in `routes.py`, never mounted |
| V1 schemas | 🚫 Commented out in `request.py` (`ErrorResponse` shared) |
| `predictor.py` / `rules.py` | 🚫 Banner-marked deprecated |
| `training/` (preprocess/train/evaluate) | 🚫 Deprecated; V2 training is `armd_model/` |
| `backend/model/` artifacts | Present but not loaded here |
| Frontend `ResultCard` (SHAP) | 🚫 Commented out |

To work on V1, switch to `main`.

---

## Local Setup Checklist

### Prerequisites
- [ ] Python 3.11+, Node 20+, npm 10+, Git

### 1 — Clone & configure
```bash
git clone https://github.com/EponymousBearer/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
git checkout version/v2_release
cp .env.example .env
```

### 2 — Backend (artifacts are committed; no training needed)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # scikit-learn==1.3.2
uvicorn app.main:app --reload --port 8000
```
- [ ] `http://localhost:8000/health` → healthy
- [ ] `http://localhost:8000/api/v2/model-info` → `available: true`

### 3 — Frontend
```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```
- [ ] `http://localhost:3000` loads; submitting the form returns top 3 results

### 4 — (Optional) retrain V2
```bash
ls datasets/   # 6 ARMD CSVs + d_dose.csv
cd armd_model && pip install -r requirements.txt
python train_armd.py && python build_antibiogram.py && python train_dosage.py
```

### Docker alternative
```bash
docker-compose up --build
```

---

## File Inventory

### V2 pipeline files
| File | Purpose |
|---|---|
| `armd_model/train_armd.py` | RF recommender training |
| `armd_model/build_antibiogram.py` | Organism→antibiotic antibiogram (CLSI M39) |
| `armd_model/train_dosage.py` | Hybrid dosage model training |
| `armd_model/requirements.txt` | Training dependencies |
| `backend/app/services/armd_predictor.py` | RF inference + antibiogram + ranking |
| `backend/app/services/dosage_service.py` | Hybrid dosage service |
| `backend/app/services/clinical_catalog.py` | Culture→organism catalog + validation |
| `frontend/components/PatientForm.tsx` | V2 clinical input form |
| `frontend/components/ResultCardV2.tsx` | V2 recommendation card |

> The two `docs/*.py` files (`armd_randomforest_top3_recommendation.py`, `dosage_model.py`) are the original Colab notebooks, reference only.

### Documentation
| File | Status |
|---|---|
| `README.md` | ✅ V2-primary; full detail; V1 legacy note |
| `docs/MODEL.md` | ✅ V2 first (verified numbers); V1 legacy |
| `docs/API_REFERENCE.md` | ✅ V2 endpoints; V1 listed as disabled |
| `docs/ARCHITECTURE.md` | ✅ V2 services + 3-layer engine |
| `docs/DEPLOYMENT.md` | ✅ V2 deploy; sklearn pin; Render/Vercel |
| `docs/BUILD_STATUS.md` | ✅ This file |
| `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md` / `.env.example` | ✅ |

---

## Known Issues

| Issue | Severity | Status | Workaround |
|---|---|---|---|
| Artifacts must be regenerated after dataset changes | Operational | ✅ Current artifacts present | Run the 3 training scripts |
| sklearn version mismatch breaks unpickling | High | ✅ Pinned 1.3.2 | Keep backend env on `scikit-learn==1.3.2` |
| Per-prediction SHAP not available (V2) | Minor | ⏳ Planned | Use global `feature_importances.joblib` |
| Prior-history features default to 0 | Moderate | ⏳ Planned | Not yet captured in the UI |
| Sparse organism dropdown when cohort CSV absent | Minor | 🔧 | Provide cohort CSV or set `ARMD_COHORT_PATH` |

---

## Pending Work

### Medium priority
- [ ] Per-prediction TreeSHAP explainability in `ResultCardV2`
- [ ] Prior antibiotic-class / prior-organism fields in the V2 form (advanced section)
- [ ] Persist Top-3 hit-rate / MRR into artifacts and surface on the dashboard

### Low priority
- [ ] Calibrate V2 probabilities (isotonic / Platt)
- [ ] Concept-drift detection + automated retraining
- [ ] Add `manual_test_cases_unambiguous.csv` to `datasets/` for dosage batch eval
- [ ] External validation on an independent hospital dataset
- [ ] Auth + audit logging; polymicrobial-infection support
