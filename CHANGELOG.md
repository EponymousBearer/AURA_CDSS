# Changelog

All notable changes to AURA are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2024-12-01

### Added

**Backend**
- FastAPI application with Uvicorn, full CORS configuration, and structured logging.
- `POST /api/v1/recommend` — CatBoost susceptibility prediction + rule-based dosing for top 3 antibiotics.
- `POST /api/v1/explain` and `GET /api/v1/explain` — SHAP feature importance for individual antibiotic predictions.
- `GET /api/v1/organisms` — Enumerated list of 13 supported bacterial organisms.
- `GET /api/v1/antibiotics` — Available antibiotic list derived from loaded model.
- `GET /api/v1/model-info` — Model inventory, per-antibiotic AUC/F1/accuracy, and training metadata.
- `GET /health` — Liveness probe compatible with Render, Docker, and Kubernetes.
- `X-Request-ID` tracing header propagated through every API response.
- Pydantic v2 request/response schemas with full validation and OpenAPI examples.
- `DosingRuleEngine` — 20+ antibiotic dosing entries with IV/PO route selection, four-tier renal adjustment (normal/mild/low/severe), and severity-based duration extension.
- `PredictionService` — CatBoost model loader, organism normalisation, baseline-correction ranking, organism compatibility weighting, and SHAP explainability.
- Global exception handler with environment-aware detail disclosure.
- Non-root Docker user (`appuser:1000`), healthcheck, and multi-stage build.
- Vercel serverless handler (`api/index.py`) and `backend/vercel.json`.
- Render free-tier deployment blueprint (`render.yaml`).

**Frontend**
- Next.js 14 App Router with TypeScript and Tailwind CSS.
- Home page — hero section, patient form, result cards, resistance chart, clinical disclaimer.
- `PatientForm` — organism selector, age/gender/kidney_function/severity inputs, inline validation, reset.
- `ResultCard` — rank badge, susceptibility probability bar, dosing block, expandable SHAP modal.
- `ResistanceChart` — all-antibiotic bar chart with colour-coded probability tiers.
- `DisclaimerBanner` — reusable academic-use warning component.
- `/model-info` page — summary cards (antibiotic count, avg AUC, training samples) and per-antibiotic quality table.
- Axios API client with 30-second timeout and snake_case/camelCase normalisation.
- Result timestamp and request retry support.
- Multi-stage Docker build with non-root user (`nextjs:1001`).
- Vercel deployment configuration.

**Training Pipeline**
- `preprocess.py` — Dryad CSV loading, organism normalisation, age-bucket parsing, synthetic clinical feature assignment, train/val/test split (70/15/15).
- `train.py` — `AntibioticPredictorTrainer` with per-antibiotic binary CatBoostClassifier, 5-fold cross-validation, class-imbalance weighting, quality filter (AUC ≥ 0.65), and artifact export (pickle + JSON).
- `evaluate.py` — Held-out test evaluation, confusion matrices, readable tables, JSON report export.
- 22,946 training samples across 23 antibiotic classifiers.
- 3 antibiotics excluded: Ethambutol (degenerate), Colistin (AUC 0.50), Cefpodoxime (AUC 0.50).

**Infrastructure**
- `docker-compose.yml` — backend + frontend with healthcheck dependency.
- GitHub Actions CI (`ci.yml`) — lint and test on push/PR.
- `Makefile` with common development targets.
- `.env.example` with all documented environment variables.

---

## [Unreleased]

### Added
- **Antibiogram clinical filter** (`armd_model/build_antibiogram.py` → `organism_antibiotic_panel.json`) — restricts candidate antibiotics to those a lab actually tests for the organism (CLSI M39 ≥30 isolates; 85 organisms). Applied as Layer 2 of the recommendation engine so clinically nonsensical drugs can never top the ranking.

### Changed
- **V1 (CatBoost) disabled on `version/v2_release`** — routes, services, and schemas commented out (not deleted); only `/api/v2/*` is mounted. V1 remains the live product on `main`.
- Backend now deploys from `backend/Dockerfile` (Render) and the frontend via Vercel **Root Directory = `frontend`**; root `vercel.json` and `render.yaml` removed to fix deploy/404 conflicts.
- Documentation (`README.md` + all `docs/*.md`) rewritten to be V2-primary with verified numbers; V1 kept as a legacy note.

### Fixed
- Pinned **`scikit-learn==1.3.2`** — newer versions fail to unpickle the shipped artifacts (`SimpleImputer has no attribute _fill_dtype`), which 500'd `/api/v2/recommend`.
- Lab values now merge correctly (`median_wbc`→`wbc_median` rename; `'Null'` parsed as NaN).
- Dosage resolution maps culture site → disease (urine→UTI, blood→Bacteremia, respiratory→Pneumonia) and never surfaces "unknown".

### Planned

- Capture prior antibiotic class exposure and prior organism history in the V2 UI form.
- Per-prediction TreeSHAP explainability for the V2 RandomForest model.
- Probability calibration (Platt scaling / isotonic regression).
- Concept drift detection and automated retraining pipeline.
- User authentication and audit logging.
- External validation on an independent hospital dataset.
- Multi-organism polymicrobial infection support.

---

## [2.0.0] — 2025-04-01

### Added

**Backend — V2 ARMD RandomForest pipeline**
- `POST /api/v2/recommend` — ARMD RandomForest susceptibility prediction (32 antibiotics) with hybrid dosage (exact lookup → RF fallback → static fallback table).
- `GET /api/v2/organisms` — Culture sites and valid organism list for the V2 form.
- `GET /api/v2/model-info` — RF model inventory, held-out test results, global feature importances, and dosage model status.
- `ARMDPredictorService` — loads RF pipeline + metadata; injects antibiotic as a feature; scores all 32 candidates per request; tuned threshold (0.50, balanced policy).
- `DosageService` — three-tier fallback chain: exact lookup table (840 rows) → RF dose/route models → static fallback dosing table (never returns "unknown").
- `ClinicalCatalogService` — organism / culture-site mappings for the V2 form dropdowns.
- Ward-to-binary-flag mapping (`general/icu/er` → `ward__ip/icu/er`).
- HTTP 503 with actionable instructions when V2 artifacts are absent.
- `ARMDRecommendationRequest`, `ARMDResult`, `ARMDRecommendationResponse`, `WardEnum` Pydantic schemas.

**Frontend — V2 interface**
- `PatientForm` component — culture site, organism, age, gender, WBC, creatinine, lactate, procalcitonin, ward inputs.
- `ResultCardV2` component — probability bar, dose range, route badge, dose source indicator.
- Home page rewired to V2 `POST /api/v2/recommend`; shared `ResistanceChart` retained.
- HTTP 503 error message with inline training command shown to the user.

**Training pipeline — V2 ARMD**
- `armd_model/train_armd.py` — merges 6 ARMD CSV files (joined on `anon_id`), engineers 46 features, patient-grouped split (`GroupShuffleSplit`), trains `RandomForestClassifier` (150 trees, max_depth=16, min_samples_leaf=4, balanced_subsample), tunes decision threshold on validation split (balanced policy → 0.50), evaluates on held-out test split (ROC AUC 0.851, F1 0.862, recall 0.794, precision 0.942, accuracy 0.788).
- `armd_model/train_dosage.py` — builds exact lookup table from `d_dose.csv` and trains RF fallback models (500 trees) for unseen `(generic, disease, age_group)` combinations.
- `armd_model/requirements.txt` — isolated training dependencies.

**Documentation**
- `docs/MODEL.md` — V2 ARMD dataset, feature schema, model design, threshold tuning, evaluation, dosage model, and inference pipeline.
- `docs/API_REFERENCE.md` — V2 endpoint specifications.
- `docs/ARCHITECTURE.md` — updated component map and data-flow diagram for V2.
- `docs/BUILD_STATUS.md` — full feature tracker for V1 and V2.
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `LICENSE` — added.
- `CODE_OF_CONDUCT.md`, `CITATION.cff` — added for open-source readiness.
- GitHub issue templates and PR template added.

**Infrastructure**
- `render.yaml` — Render free-tier backend blueprint. *(Later removed — see [Unreleased]; backend now deploys from `backend/Dockerfile`.)*
- `vercel.json` — Vercel frontend deployment configuration. *(Root config later removed — see [Unreleased]; frontend now uses Root Directory = `frontend`.)*
- `.gitignore` updated — datasets, model artifacts, and training outputs excluded; Google Drive link embedded for dataset access.
