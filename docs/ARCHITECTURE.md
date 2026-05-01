# Architecture

This document describes the system design, component responsibilities, data flow, and key architectural decisions for AURA v1.

---

## Contents

- [System Overview](#system-overview)
- [Component Map](#component-map)
- [Request Flow](#request-flow)
- [Backend Structure](#backend-structure)
- [Frontend Structure](#frontend-structure)
- [Data Layer](#data-layer)
- [Deployment Topology](#deployment-topology)
- [Key Design Decisions](#key-design-decisions)
- [Cross-Cutting Concerns](#cross-cutting-concerns)

---

## System Overview

AURA is a three-tier web application:

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION TIER                                           │
│  Next.js 14 (TypeScript + Tailwind CSS)                      │
│  Deployed on Vercel                                          │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTPS/JSON (REST)
┌─────────────────────────▼────────────────────────────────────┐
│  APPLICATION TIER                                            │
│  FastAPI 1.0 (Python 3.11 + Uvicorn)                         │
│  Deployed on Render (or Vercel serverless)                   │
│                                                              │
│  ┌──────────────┐   ┌────────────────┐   ┌───────────────┐  │
│  │ API Routes   │   │  Prediction    │   │  Dosing Rule  │  │
│  │ /recommend   │──▶│  Service       │──▶│  Engine       │  │
│  │ /explain     │   │  (CatBoost)    │   │  (rules.py)   │  │
│  │ /model-info  │   └────────────────┘   └───────────────┘  │
│  └──────────────┘                                            │
└─────────────────────────┬────────────────────────────────────┘
                          │ File I/O (pickle / JSON)
┌─────────────────────────▼────────────────────────────────────┐
│  DATA TIER                                                   │
│  model/antibiotic_model.pkl   (23 CatBoost classifiers)      │
│  model/model_metadata.json    (training metadata + metrics)  │
└──────────────────────────────────────────────────────────────┘
```

There is no live database. The trained model is serialised to disk once during training and loaded into memory at server startup.

---

## Component Map

### Backend (`backend/app/`)

```
main.py
│  FastAPI application factory
│  CORS middleware
│  Request logging + timing middleware
│  Global exception handler
│  Startup event (model load check)
│
├─ api/routes.py
│    POST /recommend  — orchestrates predictor → rules → response
│    POST /explain    — delegates to predictor.get_feature_importance_for_prediction
│    GET  /explain    — same, query-string variant
│    GET  /organisms  — enumerates OrganismEnum values
│    GET  /antibiotics — asks prediction_service for available list
│    GET  /model-info  — delegates to prediction_service.get_model_info
│
├─ schemas/request.py
│    OrganismEnum          14 allowed organisms
│    GenderEnum            M | F
│    KidneyFunctionEnum    normal | mild | low | severe
│    SeverityEnum          low | medium | high | critical
│    AntibioticRecommendationRequest
│    AntibioticResult
│    AntibioticPrediction
│    AntibioticRecommendationResponse
│    AntibioticExplainRequest
│    ErrorResponse
│
├─ services/predictor.py   (PredictionService)
│    __init__              loads pickle, sets antibiotic_list
│    predict               builds DataFrame, calls predict_proba per model
│    rank_antibiotics      baseline correction + organism compatibility weight
│    get_feature_importance_for_prediction   CatBoost SHAP values
│    get_available_antibiotics
│    get_model_info        reads model_metadata.json
│
└─ services/rules.py       (DosingRuleEngine)
     __init__              populates dosing_db (~20 antibiotics)
     get_dosing            route + dose + frequency + duration + notes
     _determine_route      IV for high/critical, PO if available otherwise
     _adjust_for_renal     four-tier lookup (normal/mild/low/severe)
     _adjust_duration      severity-based extension
```

### Frontend (`frontend/`)

```
app/
│
├─ layout.tsx              Root layout, Space Grotesk font, metadata
│
├─ page.tsx                Home page
│    State: formData, recommendations, loading, error
│    Flow:  PatientForm → api.getRecommendation() → ResultCard[]
│                                                 → ResistanceChart
│
└─ model-info/page.tsx     Model dashboard
     Fetches: api.getModelInfo()
     Renders: summary cards + per-antibiotic quality table

components/
│
├─ PatientForm.tsx          Controlled form, inline validation, submit/reset
├─ ResultCard.tsx           Rank badge, probability bar, dosing, SHAP modal
├─ ResistanceChart.tsx      All-antibiotic bar chart (colour-coded tiers)
├─ DisclaimerBanner.tsx     Reusable warning banner
└─ index.ts                 Barrel export

services/
└─ api.ts                   Axios client (base URL from NEXT_PUBLIC_API_URL)
                             getRecommendation, getOrganisms, getAntibiotics,
                             getExplanation, getModelInfo

types/
└─ index.ts                 PatientFormData, Recommendation, RecommendationResponse,
                            ExplainabilityModalData, ResistanceChartProps
```

---

## Request Flow

### Happy path: `POST /recommend`

```
Browser
  │ 1. User submits PatientForm
  ▼
api.ts : getRecommendation(formData)
  │ 2. POST /api/v1/recommend  { organism, age, gender, kidney_function, severity }
  ▼
routes.py : get_recommendation()
  │ 3. Generate request_id (UUID)
  │ 4. _validate_age()               → 400 if age < 0 or > 150
  │ 5. prediction_service.predict()  → Dict[antibiotic, raw_probability]
  │ 6. prediction_service.rank_antibiotics() → top 3 (antibiotic, adjusted_prob)
  │ 7. dosing_engine.get_dosing() × 3
  │ 8. Build AntibioticRecommendationResponse
  │ 9. Set X-Request-ID header
  ▼
Browser receives JSON
  │ 10. page.tsx sets recommendations state
  │ 11. Renders ResultCard × 3  +  ResistanceChart
  ▼
User reads results

Optional: SHAP explain
  │ 12. User clicks "Explain" on ResultCard
  │ 13. GET /api/v1/explain?...
  ▼
routes.py : explain_recommendation_get()
  │ 14. prediction_service.get_feature_importance_for_prediction()
  ▼
Browser receives { feature: shap_value, ... }
  │ 15. ResultCard renders expandable SHAP modal
```

### Organism label normalisation

The Dryad training data uses uppercase labels (e.g. `"ESCHERICHIA COLI"`). The UI and API use clinical shorthand (e.g. `"E. coli"`). `PredictionService` maintains a bidirectional mapping applied before feature construction.

---

## Backend Structure

### Middleware stack (outermost → innermost)

1. `CORSMiddleware` — validates `Origin` against `ALLOWED_ORIGINS`.
2. `logging_middleware` — logs method/path on entry, status/duration on exit.
3. Route handler — Pydantic validation, business logic.
4. `global_exception_handler` — catches unhandled exceptions, returns HTTP 500.

### Service initialisation

Both `PredictionService` and `DosingRuleEngine` are instantiated at module import time inside `routes.py`. Model loading happens once at startup; subsequent requests reuse the in-memory model objects.

### Model loading

```
PredictionService.__init__()
  ├── Tries MODEL_PATH env var, then relative backend/model/antibiotic_model.pkl
  ├── pickle.load() → { models, antibiotic_list, categorical_features, positive_rates }
  └── Falls back to simplified prediction patterns if file is missing
```

If the model is unavailable the service logs a warning and operates in fallback mode — returning synthetic probability patterns. This prevents a hard startup failure during development.

---

## Frontend Structure

### State management

The application uses React's built-in `useState`/`useEffect`. There is no global state store. Data flows:

```
page.tsx (state owner)
  ├── formData          → PatientForm (props)
  ├── recommendations   → ResultCard[] (props)
  ├── allPredictions    → ResistanceChart (props)
  ├── loading           → PatientForm (submit button disabled)
  └── error             → inline error display
```

### API client

`services/api.ts` exports named functions wrapping Axios:

```typescript
getRecommendation(data: PatientFormData): Promise<RecommendationResponse>
getOrganisms(): Promise<string[]>
getAntibiotics(): Promise<string[]>
getExplanation(params): Promise<Record<string, number>>
getModelInfo(): Promise<ModelInfo>
```

The base URL is read from `process.env.NEXT_PUBLIC_API_URL` at build time, defaulting to `http://localhost:8000`.

---

## Data Layer

### Trained model artifacts

| File | Format | Contents |
|---|---|---|
| `backend/model/antibiotic_model.pkl` | Python pickle | Dict with `models` (CatBoostClassifier per antibiotic), `antibiotic_list`, `categorical_features`, `positive_rates` |
| `backend/model/model_metadata.json` | JSON | `trained_at`, `n_antibiotics`, `training_samples`, `antibiotics` array with per-antibiotic metrics |

### Training data

| File | Rows (approx.) | Purpose |
|---|---|---|
| `training/microbiology_cultures_demographics.csv` | ~30k | Dryad source — patient demographics |
| `training/microbiology_cultures_microbial_resistance.csv` | ~30k | Dryad source — culture/sensitivity results |
| `training/data/train.csv` | ~16k | 70% split, used for CatBoost training |
| `training/data/val.csv` | ~3.4k | 15% split, used for CV monitoring |
| `training/data/test.csv` | ~3.4k | 15% split, held out for final evaluation |

### Feature schema

Each training row has five input columns and one binary label column per antibiotic:

| Column | Type | Notes |
|---|---|---|
| `organism` | categorical | Normalised organism name |
| `age` | numeric | Age in years (bucket midpoint) |
| `gender` | categorical | M / F |
| `kidney_function` | categorical | Synthetically assigned |
| `severity` | categorical | Synthetically assigned |
| `<antibiotic_name>` | binary (0/1) | Susceptibility label per antibiotic |

---

## Deployment Topology

### Local development (Docker Compose)

```
docker-compose.yml
│
├── backend  (python:3.11-slim, port 8000)
│   └── healthcheck: GET /health every 30s
│
└── frontend (node:20-alpine, port 3000)
    └── depends_on: backend (service_healthy)
    └── API_URL=http://backend:8000 (internal Docker network)
        NEXT_PUBLIC_API_URL=http://localhost:8000 (browser-facing)
```

### Production (Vercel + Render)

```
Browser
  │ HTTPS
  ▼
Vercel (frontend)
  vercel.json → Next.js build from frontend/
  NEXT_PUBLIC_API_URL=https://aura-cdss-backend.onrender.com
  │
  │ HTTPS API calls
  ▼
Render (backend)
  render.yaml → python 3.11.9
  startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ALLOWED_ORIGINS=https://aura-cdss-frontend.vercel.app
```

### Alternative: Vercel serverless backend

```
backend/vercel.json → routes all requests to api/index.py
api/index.py        → imports FastAPI app
```

---

## Key Design Decisions

### 1 — One binary classifier per antibiotic

A multi-class model over all antibiotics would conflate very different resistance mechanisms and fail with missing labels. Per-antibiotic binary models allow independent quality filtering (exclude antibiotics that don't train well), independent SHAP attribution, and independent deployment.

### 2 — CatBoost

CatBoost handles categorical features natively without one-hot encoding, which is important for `organism` (14 classes) and other categoricals. It also provides built-in SHAP values through `get_feature_importance(type='ShapValues')`.

### 3 — Ranking with baseline correction

Raw `predict_proba` scores are biased by class prevalence. An antibiotic that is almost always susceptible (e.g. Vancomycin against Gram-positives in this dataset) would dominate regardless of the patient-specific factors. The predictor subtracts the training positive rate (`positive_rates[antibiotic]`) from each score before ranking, giving preference to antibiotics that are *more susceptible than their baseline* for this patient profile.

### 4 — Rule-based dosing layer

The ML model predicts susceptibility, not dosage. Dosing is clinical knowledge that changes with renal function and infection severity. Keeping it as an explicit rule engine (rather than training it) makes the dosing logic transparent, auditable, and easy to update without retraining the model.

### 5 — Synthetic clinical features

The Dryad dataset does not contain kidney function or severity. The preprocessing pipeline assigns these synthetically for modeling purposes. This is clearly documented and limits the system to academic use. The architecture is designed so that replacing synthetic assignment with real intake data is a change only to `preprocess.py`.

### 6 — Fallback prediction mode

`PredictionService` falls back to rule-based synthetic predictions if the model file is missing. This prevents a hard startup crash during frontend-only development or CI environments where the model artifact is not available.

---

## Cross-Cutting Concerns

### Logging

`app/utils/logger.py` configures a console handler (and optional file handler) with format:
```
2024-11-15 14:32:10 [INFO] app.api.routes: [request_id=abc123] Processing recommendation...
```

Every significant event is logged with a `request_id` for correlation.

### Request tracing

Every route handler generates a UUID `request_id` and attaches it to the `X-Request-ID` response header. Error responses also include it. Frontend logging on errors can capture this header for support tracing.

### Validation

Pydantic v2 validates all request payloads before reaching route logic. Enum constraints reject unknown organism/gender/kidney_function/severity values with HTTP 422. Age range is validated separately with HTTP 400 (to provide a more descriptive error message).

### CORS

The `ALLOWED_ORIGINS` environment variable is parsed at startup. In development it defaults to `http://localhost:3000`. In production it must be set to the exact Vercel frontend URL.
