# Architecture

System design, component responsibilities, data flow, and key decisions for AURA. This document describes the **active V2 (ARMD RandomForest)** system on `version/v2_release`. V1 (CatBoost) is the separate `main`-branch product and is commented out here; see the [legacy note](#v1-legacy-note).

---

## Contents

- [System Overview](#system-overview)
- [Backend Components](#backend-components)
- [The 3-layer recommendation engine](#the-3-layer-recommendation-engine)
- [Request Flow](#request-flow)
- [Frontend Components](#frontend-components)
- [Data Layer](#data-layer)
- [Deployment Topology](#deployment-topology)
- [Key Design Decisions](#key-design-decisions)
- [Cross-Cutting Concerns](#cross-cutting-concerns)
- [V1 legacy note](#v1-legacy-note)

---

## System Overview

AURA is a three-tier web application with no live database. Models are serialised to disk during training and loaded into memory at server startup.

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION TIER                                            │
│  Next.js 14 (TypeScript + Tailwind CSS) — deployed on Vercel  │
│  PatientForm → ResultCardV2 ×3 + ResistanceChart              │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTPS / JSON (REST)
┌─────────────────────────▼────────────────────────────────────┐
│  APPLICATION TIER                                             │
│  FastAPI 0.104 (Python 3.11 + Uvicorn) — deployed on Render   │
│  Mounts ONLY /api/v2/* (+ / and /health)                      │
│                                                              │
│  ┌──────────────┐  ┌──────────────────────┐  ┌────────────┐  │
│  │ v2_router    │  │ ARMDPredictorService │  │ Dosage     │  │
│  │ /recommend   │─▶│ (RF + antibiogram,   │─▶│ Service    │  │
│  │ /organisms   │  │  3-layer engine)     │  │ (hybrid)   │  │
│  │ /model-info  │  └──────────────────────┘  └────────────┘  │
│  └──────────────┘  ┌──────────────────────┐                  │
│                    │ ClinicalCatalog      │                  │
│                    │ Service (dropdowns)  │                  │
│                    └──────────────────────┘                  │
└─────────────────────────┬────────────────────────────────────┘
                          │ File I/O (joblib / json / csv)
┌─────────────────────────▼────────────────────────────────────┐
│  DATA TIER — armd_model/artifacts/                            │
│  rf_top3_recommender_optimized.joblib   (RF pipeline)         │
│  organism_antibiotic_panel.json         (antibiogram filter)  │
│  dose_route_lookup.csv + dose/route_model_hybrid.pkl          │
│  feature_cols / selected_antibiotics / best_threshold / ...   │
│  datasets/microbiology_cultures_cohort.csv  (runtime catalog) │
└──────────────────────────────────────────────────────────────┘
```

---

## Backend Components

`backend/app/`

```
main.py
│  FastAPI app, CORS middleware, request logging+timing, global exception handler
│  Startup event logs v2 model load status
│  Mounts ONLY v2_router at /api/v2  (V1 router import + mount are commented out)
│
├─ api/routes.py
│    v2_router:
│      GET  /organisms   → ClinicalCatalogService.get_catalog()
│      POST /recommend   → validate → ARMDPredictorService.predict() → DosageService
│      GET  /model-info  → armd_service + dosage_service model info
│    (V1 router + handlers present but commented out)
│
├─ schemas/request.py
│    WardEnum (general|icu|er), ARMDRecommendationRequest, ARMDResult,
│    ARMDRecommendationResponse, ErrorResponse
│    (V1 schemas commented out; ErrorResponse shared)
│
├─ services/armd_predictor.py  (ARMDPredictorService)
│    _load_artifacts   loads RF pipeline, feature_cols, threshold, metadata,
│                      test summary, importances, antibiogram panel
│    predict           the 3-layer engine (below)
│    get_model_info    inventory + metrics + feature groups + importances
│
├─ services/dosage_service.py  (DosageService)
│    _load_artifacts   loads dose_route_lookup.csv + dose/route RF models
│    get_dosage        site→disease map, age_group bucket,
│                      Tier1 lookup → Tier2 ML → Tier3 static fallback
│
├─ services/clinical_catalog.py  (ClinicalCatalogService)
│    builds culture-site → organism dropdown from the cohort CSV
│    is_valid_culture_site / is_valid_organism_for_culture  (request validation)
│
└─ services/predictor.py, rules.py   ← V1 CatBoost (DEPRECATED, banner-marked)
```

All three V2 services are instantiated once at import time in `routes.py`; artifacts load once at startup and are reused per request.

---

## The 3-layer recommendation engine

`ARMDPredictorService.predict()` is the heart of the system:

```
Layer 1 — Probability scoring
  For each candidate antibiotic, build a 46-feature row from the patient context
  (antibiotic injected as a feature; prior-history features = 0), run the RF
  pipeline → P(susceptible = 1).

Layer 2 — Antibiogram clinical filter
  Keep only antibiotics in the organism's allowed panel
  (organism_antibiotic_panel.json; CLSI M39 ≥30 isolates).
  Unknown organism → fall back to all 32 antibiotics.

Layer 3 — Ranking
  Sort the allowed candidates by absolute probability.
  Top 3 → recommendations; full list → all_predictions.
```

This separation is the core safety mechanism: the model proposes (L1), the data-derived antibiogram disposes (L2), and the ranking presents (L3).

---

## Request Flow

### `POST /api/v2/recommend`

```
Browser
  │ 1. User submits PatientForm (culture, organism, age, gender, labs, ward)
  ▼
services/api.ts : getARMDRecommendation(formData)
  │ 2. POST /api/v2/recommend
  ▼
routes.py : get_v2_recommendation()
  │ 3. request_id (UUID) → X-Request-ID
  │ 4. armd_service.is_available()                  → 503 if artifacts missing
  │ 5. clinical_catalog.is_valid_culture_site()     → 422 if unsupported
  │ 6. clinical_catalog.is_valid_organism_for_culture() → 422 if invalid
  │ 7. map ward enum → ward__icu / ward__er / ward__ip
  │ 8. armd_service.predict()  → 3-layer engine → top3 + all_scores
  │ 9. dosage_service.get_dosage() × 3
  │ 10. build ARMDRecommendationResponse
  ▼
Browser
  │ 11. page.tsx sets state → ResultCardV2 × 3 + ResistanceChart
```

### Catalog prefetch

On load the frontend calls `GET /api/v2/organisms` to populate culture-site and organism dropdowns; selecting a culture site filters the organism options to those actually seen at that site.

---

## Frontend Components

`frontend/`

```
app/
├─ layout.tsx              Root layout, fonts, metadata
├─ page.tsx                Home — owns state; PatientForm → ResultCardV2[] + ResistanceChart
└─ model-info/page.tsx     Dashboard — fetches /api/v2/model-info

components/
├─ PatientForm.tsx         V2 form: culture, organism, age, gender, ward, optional labs
├─ ResultCardV2.tsx        Probability bar + dose range + route + dose_source
├─ ResistanceChart.tsx     All scored antibiotics, ranked
├─ DisclaimerBanner.tsx    Reusable warning banner
├─ ResultCard.tsx          V1 SHAP card (commented out)
└─ index.ts                Barrel export

services/api.ts            Axios client: getARMDRecommendation, getARMDOrganismCatalog,
                           getARMDModelInfo  (base URL from NEXT_PUBLIC_API_URL)
types/index.ts             ARMDFormData, ARMDRecommendation(Response), WardType, ...
```

State is plain React `useState`/`useEffect`; no global store. `page.tsx` owns `formData`, `recommendations`, `allPredictions`, `loading`, `error`.

---

## Data Layer

### V2 artifacts (loaded at startup)

| File | Format | Contents |
|---|---|---|
| `rf_top3_recommender_optimized.joblib` | joblib | RF pipeline (preprocessor + classifier), `compress=3` |
| `feature_cols.joblib` | joblib | Ordered 46-column feature list |
| `selected_antibiotics.joblib` | joblib | 32 antibiotic names |
| `best_threshold.joblib` | joblib | Tuned threshold (0.5) |
| `metadata_optimized.json` | json | Feature groups, hyperparameters, threshold policy |
| `feature_importances.joblib` | joblib | Per-feature importance |
| `split_test_summary.joblib` | joblib | Held-out test metrics |
| `organism_antibiotic_panel.json` | json | Antibiogram filter (organism → allowed drugs) |
| `dose_route_lookup.csv` | csv | Exact `(generic, disease, age_group)` → dose/route |
| `dose_model_hybrid.pkl` / `route_model_hybrid.pkl` | joblib | Dosage RF fallbacks |

### Runtime data

`datasets/microbiology_cultures_cohort.csv` is read by `ClinicalCatalogService` at startup to build the organism dropdown (resolved via `ARMD_COHORT_PATH`). If absent, a small built-in fallback catalog is used.

### Training data

The six ARMD CSVs + `d_dose.csv` in `datasets/` (not committed — see [DEPLOYMENT.md](DEPLOYMENT.md)). Joined on `anon_id`. See [MODEL.md](MODEL.md#v2-data-pipeline--feature-engineering).

---

## Deployment Topology

### Local (Docker Compose)

```
docker-compose.yml
├─ backend  (built from backend/Dockerfile, port 8000, healthcheck GET /health)
│           artifacts under armd_model/artifacts/ are committed and loaded at startup
└─ frontend (node:20, port 3000, depends_on backend healthy)
            NEXT_PUBLIC_API_URL=http://localhost:8000 (browser)
            API_URL=http://backend:8000 (internal)
```

### Production (Vercel + Render)

```
Browser ── HTTPS ──▶ Vercel (frontend)
                     Root Directory = frontend  (no root vercel.json)
                     NEXT_PUBLIC_API_URL = https://<render-backend-url>
                          │ HTTPS
                          ▼
                     Render (backend)
                     built from backend/Dockerfile (free tier, 512 MB)
                     ALLOWED_ORIGINS = https://<vercel-frontend-url>
```

> There is no root `vercel.json` or `render.yaml` (both were removed to fix deploy conflicts). The backend deploys from `backend/Dockerfile`; the frontend deploys with **Root Directory = `frontend`**. A `backend/vercel.json` + `backend/api/index.py` serverless variant exists but is not the recommended path (model size / cold starts).

---

## Key Design Decisions

1. **Single RF with `antibiotic` as a feature** (not per-antibiotic models) — lets one model score any drug for any organism and learn organism × antibiotic interactions; the dosage models reuse the same feature space.
2. **One-hot, not ordinal, encoding** — so the forest can split on a specific organism/antibiotic/culture value instead of collapsing categoricals to a global prior.
3. **Antibiogram filter as a separate layer** — clinical correctness (CLSI M39 ≥30 isolates) is enforced *outside* the model, so a high model score can never surface a drug the lab never tests for that organism.
4. **Hybrid dosage with a static floor** — exact lookup → ML fallback → static table guarantees the API never returns "unknown".
5. **Patient-grouped splitting** — `GroupShuffleSplit` by `anon_id` prevents leakage and keeps metrics honest.
6. **Artifacts sized for free hosting** — 150 trees / depth 16 / `compress=3` keeps the model within Render's 512 MB and GitHub's 100 MB limits.
7. **Pinned `scikit-learn==1.3.2`** — the artifacts must unpickle in the backend; newer sklearn breaks unpickling.

---

## Cross-Cutting Concerns

- **Logging** — `app/utils/logger.py` configures a console handler; the HTTP middleware logs method/path on entry and status/duration on exit.
- **Request tracing** — every handler generates a UUID and returns it as `X-Request-ID` (also on errors).
- **Validation** — Pydantic v2 validates payloads; unsupported culture sites/organisms return `422`; missing model artifacts return `503`.
- **CORS** — `ALLOWED_ORIGINS` (comma-separated) parsed at startup; defaults to `http://localhost:3000`.

---

## V1 legacy note

V1 is the CatBoost product on `main`: a three-tier app where `PredictionService` (23 per-antibiotic CatBoost classifiers) and a rule-based `DosingRuleEngine` serve `/api/v1/*`, with SHAP explainability and baseline-correction + organism-compatibility ranking. On this branch the V1 router, services, and schemas are commented out and never mounted. To work on V1, switch to `main`. Details: [MODEL.md](MODEL.md#v1-legacy--catboost-on-main).
