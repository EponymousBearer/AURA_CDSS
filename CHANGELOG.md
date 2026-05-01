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
- `POST /api/v2/recommend` — ARMD RandomForest susceptibility prediction (32 antibiotics) with hybrid dosage (exact lookup → RF fallback → rule engine).
- `GET /api/v2/organisms` — Culture sites and valid organism list for the V2 form.
- `GET /api/v2/model-info` — RF model inventory, held-out test results, global feature importances, and dosage model status.
- `ARMDPredictorService` — loads RF pipeline + metadata; injects antibiotic as a feature; scores all 32 candidates per request; applies tuned threshold (0.23).
- `DosageService` — three-tier fallback chain: exact lookup table (45 k rows) → RF dose/route models → V1 rule engine.
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
- `armd_model/train_armd.py` — merges 6 ARMD CSV files, engineers 42 features, trains `RandomForestClassifier` (300 trees, max_depth=18, balanced_subsample), tunes decision threshold on validation split (recall-first, min precision 0.85), evaluates on held-out test split (ROC AUC 84.5 %, F1 91.8 %, recall 99.5 %).
- `armd_model/train_dosage.py` — builds exact lookup table from `d_dose.csv` and trains RF fallback models for unseen antibiotic/organism combinations.
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
- `render.yaml` — Render free-tier backend blueprint.
- `vercel.json` — Vercel frontend deployment configuration.
- `.gitignore` updated — datasets, model artifacts, and training outputs excluded; Google Drive link embedded for dataset access.
