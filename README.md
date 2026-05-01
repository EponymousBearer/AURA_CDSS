# AURA — Antibiotic AI Clinical Decision Support System

[![Build](https://img.shields.io/badge/build-passing-brightgreen)](#)
[![Backend](https://img.shields.io/badge/backend-FastAPI%201.0-009688?logo=fastapi)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js%2014-111827?logo=next.js)](#)
[![v1 Model](https://img.shields.io/badge/v1-CatBoost-ff7f0e)](#)
[![v2 Model](https://img.shields.io/badge/v2-RandomForest%20ARMD-4caf50)](#)
[![License](https://img.shields.io/badge/license-MIT-blue)](#)
[![Python](https://img.shields.io/badge/python-3.11-blue?logo=python)](#)
[![Node](https://img.shields.io/badge/node-20-brightgreen?logo=node.js)](#)

> **For academic and research use only. Not for autonomous clinical prescribing.**

AURA is an end-to-end clinical decision support system that predicts antibiotic susceptibility and converts those predictions into dosage recommendations. The system has two production-ready model versions running simultaneously on the same backend:

| | V1 — CatBoost | V2 — ARMD RandomForest |
|---|---|---|
| **Endpoint** | `/api/v1/recommend` | `/api/v2/recommend` |
| **Dataset** | Dryad microbiology cultures | ARMD (6-file clinical dataset) |
| **Inputs** | organism, age, gender, kidney function, severity | culture site, organism, age, gender, WBC, creatinine, lactate, procalcitonin, ward |
| **Antibiotics** | 23 (CatBoost per-antibiotic classifiers) | 32 (single RF pipeline, all scored per request) |
| **Dosing** | Rule-based engine (frequency + duration) | Hybrid lookup + ML model (dose range + route) |
| **Explainability** | SHAP per prediction | Feature importance (global) |
| **Status** | **Complete** | **Complete with trained artifacts in `armd_model/artifacts/`** |

---

## Contents

- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
- [Datasets](#datasets)
- [Training the V2 Model](#training-the-v2-model)
- [Manual Setup](#manual-setup)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Model Performance](#model-performance)
- [V2 Model Details](#v2-model-details)
- [Deployment](#deployment)
- [Build Status](#build-status)
- [Limitations](#limitations)
- [Future Work](#future-work)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser  —  Next.js 14 (TypeScript + Tailwind)                      │
│                                                                      │
│  PatientForm (v2)  →  ResultCardV2 ×3  →  ResistanceChart           │
│  (culture, organism, age, gender, labs, ward)                        │
└────────────────────────┬─────────────────────────────────────────────┘
                         │ HTTPS / JSON
┌────────────────────────▼─────────────────────────────────────────────┐
│  FastAPI 1.0  (Python 3.11)                                          │
│                                                                      │
│  /api/v1/*  ──►  PredictionService (CatBoost)                        │
│                   DosingRuleEngine                                    │
│                                                                      │
│  /api/v2/*  ──►  ARMDPredictorService (RandomForest Pipeline)        │
│                   DosageService (lookup + ML hybrid)                 │
└──────────┬───────────────────────────────┬───────────────────────────┘
           │                               │
    backend/model/                  armd_model/artifacts/
    antibiotic_model.pkl            rf_top3_recommender_optimized.joblib
    model_metadata.json             dose_model_hybrid.pkl
                                    dose_route_lookup.csv
```

---

## Repository Layout

```
antibiotic-ai-cdss/
│
├── backend/                        FastAPI backend
│   ├── app/
│   │   ├── api/routes.py           V1 + V2 API endpoints
│   │   ├── schemas/request.py      Pydantic models (v1 + v2)
│   │   ├── services/
│   │   │   ├── predictor.py        V1 CatBoost service
│   │   │   ├── rules.py            V1 rule-based dosing engine
│   │   │   ├── armd_predictor.py   V2 ARMD RF service
│   │   │   └── dosage_service.py   V2 hybrid dosage service
│   │   └── main.py                 FastAPI app + middleware
│   ├── model/                      V1 trained model artifacts
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                       Next.js 14 frontend
│   ├── app/
│   │   ├── page.tsx                Home / V2 recommendation dashboard
│   │   └── model-info/page.tsx     Model performance dashboard (v2)
│   ├── components/
│   │   ├── PatientForm.tsx         V2 clinical input form
│   │   ├── ResultCardV2.tsx        V2 recommendation card
│   │   ├── ResultCard.tsx          V1 recommendation card (with SHAP)
│   │   ├── ResistanceChart.tsx     Full antibiotic probability chart
│   │   └── DisclaimerBanner.tsx
│   ├── services/api.ts             Axios client (v1 + v2 functions)
│   ├── types/index.ts              TypeScript types (v1 + v2)
│   ├── Dockerfile
│   └── package.json
│
├── training/                       V1 CatBoost training pipeline
│   ├── preprocess.py
│   ├── train.py
│   ├── evaluate.py
│   └── requirements.txt
│
├── armd_model/                     V2 ARMD training pipeline
│   ├── train_armd.py               RF recommendation model training
│   ├── train_dosage.py             Dosage model training
│   ├── artifacts/                  Generated model artifacts (git-ignored)
│   └── requirements.txt
│
├── datasets/                       ARMD source CSV files — NOT committed
│   │                               Download from Google Drive (see below)
│   ├── microbiology_cultures_cohort.csv
│   ├── microbiology_cultures_demographics.csv
│   ├── microbiology_cultures_labs.csv
│   ├── microbiology_cultures_antibiotic_class_exposure.csv
│   ├── microbiology_culture_prior_infecting_organism.csv
│   ├── microbiology_cultures_ward_info.csv
│   └── d_dose.csv
│
├── docs/                           Extended documentation
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── MODEL.md
│   ├── DEPLOYMENT.md
│   └── BUILD_STATUS.md
│
├── docker-compose.yml
├── render.yaml
├── vercel.json
├── .env.example
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── Makefile
```

---

## Quick Start

### Docker

```bash
git clone https://github.com/EponymousBearer/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
cp .env.example .env
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

> V2 uses the artifacts in `armd_model/artifacts/`. Retrain only when replacing the ARMD datasets or model configuration.

---

## Datasets

Neither the ARMD clinical dataset nor the Dryad microbiology files are committed to this repository due to their size.

**Download all required files from Google Drive:**

> **[Google Drive — AURA Datasets](https://drive.google.com/drive/folders/1agc1hXlVinXAPM-7E8RFfAFopKVrIota?usp=sharing)**

| File | Used by | Destination |
|---|---|---|
| `microbiology_cultures_cohort.csv` | V2 training | `datasets/` |
| `microbiology_cultures_demographics.csv` | V1 + V2 training | `datasets/` (V2) · `training/` (V1) |
| `microbiology_cultures_labs.csv` | V2 training | `datasets/` |
| `microbiology_cultures_antibiotic_class_exposure.csv` | V2 training | `datasets/` |
| `microbiology_culture_prior_infecting_organism.csv` | V2 training | `datasets/` |
| `microbiology_cultures_ward_info.csv` | V2 training | `datasets/` |
| `d_dose.csv` | V2 dosage model | `datasets/` |
| `microbiology_cultures_microbial_resistance.csv` | V1 training | `training/` |

Once downloaded, place the V2 files in `datasets/` and the two V1 Dryad files in `training/` before running any training script.

---

## Training the V2 Model

The ARMD dataset files must be present in `datasets/` (they are not committed to git — see [Datasets](#datasets) above). Once the files are in place, run the two training scripts in order:

### Step 1 — Train the recommendation model

```bash
cd armd_model
pip install -r requirements.txt
python train_armd.py
```

This reads all 6 ARMD CSV files from `datasets/`, trains a RandomForest pipeline across 32 antibiotics, tunes the decision threshold on a validation split, evaluates held-out test results, and saves artifacts to `armd_model/artifacts/`:

```
armd_model/artifacts/
  rf_top3_recommender_optimized.joblib   ← main RF pipeline
  feature_cols.joblib                    ← feature column order
  selected_antibiotics.joblib            ← 32 antibiotic names
  best_threshold.joblib                  ← tuned decision threshold
  split_test_summary.joblib              ← held-out test metrics
  feature_importances.joblib
  metadata_optimized.json
```

### Step 2 — Train the dosage model

```bash
python train_dosage.py
```

This reads `datasets/d_dose.csv`, builds an exact lookup table, trains fallback RF models for unseen combinations, and saves:

```
armd_model/artifacts/
  dose_route_lookup.csv                  ← exact lookup table
  dose_model_hybrid.pkl                  ← dose range fallback model
  route_model_hybrid.pkl                 ← route fallback model
```

After both scripts complete, restart the backend and the V2 endpoint becomes fully operational.

---

## Manual Setup

### Backend (both V1 + V2)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

### V1 model retraining (optional)

Requires the two Dryad CSV files placed in `training/` — download from the [Google Drive folder](https://drive.google.com/drive/folders/1agc1hXlVinXAPM-7E8RFfAFopKVrIota?usp=sharing).

```bash
cd training
pip install -r requirements.txt
python preprocess.py
python train.py
python evaluate.py
cp training/output/antibiotic_model.pkl  backend/model/
cp training/output/model_metadata.json   backend/model/
```

### Tests

```bash
cd backend && pytest tests/ -v
```

---

## Configuration

| Variable | Default | Used by | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | Backend | Startup log label |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Backend | CORS allowlist (comma-separated) |
| `LOG_LEVEL` | `INFO` | Backend | Logging verbosity |
| `PORT` | `8000` | Backend | Uvicorn bind port |
| `MODEL_PATH` | `model/antibiotic_model.pkl` | Backend (V1) | V1 CatBoost model path |
| `MODEL_METADATA_PATH` | `model/model_metadata.json` | Backend (V1) | V1 metadata path |
| `ARMD_ARTIFACTS_DIR` | `../armd_model/artifacts` | Backend (V2) | V2 model artifacts directory |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend | Client-side API base URL |
| `API_URL` | `http://backend:8000` | Frontend (Docker) | Server-side API URL |

Copy `.env.example` to `.env` and adjust values.

---

## API Reference

Full documentation: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

### V1 endpoints (CatBoost)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/organisms` | Supported organism list (14 items) |
| `GET` | `/api/v1/antibiotics` | Available antibiotics from loaded model |
| `POST` | `/api/v1/recommend` | Top 3 recommendations + dosing + SHAP |
| `POST/GET` | `/api/v1/explain` | SHAP feature importance for one antibiotic |
| `GET` | `/api/v1/model-info` | Per-antibiotic AUC/F1/accuracy table |

**V1 request:**
```json
{
  "organism": "E. coli",
  "age": 65,
  "gender": "F",
  "kidney_function": "normal",
  "severity": "medium"
}
```

### V2 endpoints (ARMD RandomForest)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v2/recommend` | Top 3 recommendations + dose range + route |
| `GET` | `/api/v2/organisms` | Culture sites and valid organisms for the selected culture site |
| `GET` | `/api/v2/model-info` | ARMD model inventory, test results, feature importances, dosage model status |

**V2 request:**
```json
{
  "culture_description": "urine",
  "organism": "klebsiella pneumoniae",
  "age": 45,
  "gender": "female",
  "wbc": 12.5,
  "cr": 1.2,
  "lactate": 1.8,
  "procalcitonin": 2.5,
  "ward": "er"
}
```

**V2 response:**
```json
{
  "recommendations": [
    {
      "antibiotic": "meropenem",
      "probability": 0.871,
      "dose_range": "500-1000 mg",
      "route": "IV",
      "dose_source": "lookup"
    }
  ],
  "patient_factors": { ... },
  "culture_description": "urine",
  "all_predictions": [ ... ]
}
```

---

## Model Performance

The `/model-info` dashboard now tracks the V2 production workflow:

- **Recommendation model:** ARMD RandomForest pipeline, 32 antibiotics, 42 model features, tuned threshold 0.23
- **Held-out test results at threshold 0.23:** ROC AUC 84.5%, F1 91.8%, recall 99.5%, precision 85.2%, accuracy 85.2%
- **Dosage model:** hybrid exact lookup plus RandomForest fallback for dose range and route
- **Feature reporting:** categorical/numeric/binary feature groups plus top global feature importances

### V1 Model Performance

23 antibiotics trained on 22,946 Dryad samples. 3 excluded (AUC < 0.65).

| Antibiotic | AUC | F1 | Accuracy |
|---|---:|---:|---:|
| Ampicillin | 0.902 | 0.840 | 0.817 |
| Penicillin | 0.898 | 0.751 | 0.828 |
| Erythromycin | 0.836 | 0.628 | 0.739 |
| Vancomycin | 0.807 | 0.203 | 0.751 |
| Meropenem | 0.787 | 0.127 | 0.765 |
| Ciprofloxacin | 0.742 | 0.542 | 0.719 |
| Ceftriaxone | 0.710 | 0.318 | 0.583 |
| Cefazolin | 0.708 | 0.532 | 0.617 |
| Levofloxacin | 0.703 | 0.508 | 0.681 |
| *(+ 14 more)* | | | |

Full table: [`docs/MODEL.md`](docs/MODEL.md)

---

## V2 Model Details

- **Algorithm:** sklearn `RandomForestClassifier` (300 trees, max_depth=18, balanced_subsample)
- **Strategy:** Single pipeline; antibiotic is injected as a feature and scored for all 32 candidates per request
- **Threshold tuning:** Recall-first policy on validation split (min precision 0.85)
- **Feature groups:**
  - Core: `culture_description`, `organism`, `antibiotic`
  - Demographics: `age`, `gender`
  - Labs: `wbc_median`, `cr_median`, `lactate_median`, `procalcitonin_median`
  - Ward: `ward__icu`, `ward__er`, `ward__ip`
  - Prior history: `prior_abxclass__*`, `prior_org__*` (default 0 at inference)
- **32 Antibiotics:** amikacin, ampicillin, aztreonam, cefazolin, cefepime, cefotaxime, cefoxitin, cefpodoxime, ceftazidime, ceftriaxone, cefuroxime, chloramphenicol, ciprofloxacin, clarithromycin, clindamycin, doripenem, doxycycline, ertapenem, erythromycin, fosfomycin, gentamicin, levofloxacin, linezolid, meropenem, metronidazole, moxifloxacin, nitrofurantoin, streptomycin, tetracycline, tigecycline, tobramycin, vancomycin

Full methodology: [`docs/MODEL.md`](docs/MODEL.md)

---

## Deployment

Full guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

| Target | Config | Notes |
|---|---|---|
| Docker local | `docker-compose.yml` | V1 ready; V2 needs training |
| Vercel (frontend) | `vercel.json` | Auto-deploys on push to main |
| Render (backend) | `render.yaml` | Free-tier web service |
| Vercel (serverless) | `backend/vercel.json` | Size limit may exclude large models |

---

## Build Status

See [`docs/BUILD_STATUS.md`](docs/BUILD_STATUS.md) for the full feature tracker covering completed work, pending items, and known issues for both V1 and V2.

---

## Limitations

- **V1:** Some clinical features (kidney function, severity) are synthetically assigned in preprocessing. Not from real records.
- **V2:** Prior antibiotic class exposure and prior organism history features default to zero at inference (not captured in the UI). This reduces prediction precision for patients with complex histories.
- Neither version is suitable for autonomous clinical prescribing. Clinician judgment, local resistance patterns, and stewardship policies always take precedence.
- V2 requires the full ARMD dataset to retrain. Keep generated artifacts in `armd_model/artifacts/` available to the backend.

---

## Future Work

- Capture prior antibiotic exposure and prior organism history in the V2 UI form.
- Calibrate V2 probability outputs (isotonic regression / Platt scaling).
- Add per-prediction feature importance to V2 (TreeSHAP on the RF model).
- Add concept drift detection and automated retraining pipeline.
- External validation on an independent hospital dataset.
- User authentication and audit logging for compliance scenarios.
- Polymicrobial infection support.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch conventions, code style, and the PR process.

---

## References

- Prokhorenkova et al. *CatBoost: gradient boosting with categorical features support.* NeurIPS, 2018. [arXiv:1810.11363](https://arxiv.org/abs/1810.11363)
- Breiman, L. *Random Forests.* Machine Learning, 45(1), 5–32, 2001.
- IDSA Clinical Practice Guidelines. [idsociety.org](https://www.idsociety.org/practice-guideline/)
- Dryad Digital Repository. [datadryad.org](https://datadryad.org/)

---

## License

[MIT](LICENSE) © 2024 AURA Project Contributors

---

> **Disclaimer:** This project is for educational and research purposes only. It must not be used as the sole basis for antibiotic prescribing decisions. Always confirm recommendations against current microbiology results, local resistance patterns, institutional stewardship protocols, and specialist guidance.
