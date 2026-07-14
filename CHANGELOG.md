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
- Capture prior antibiotic class exposure and prior organism history in the V2 UI form (they currently default to 0 at inference).
- Replace the provisional Pakistan seed antibiogram with national PARN / NIH-Pakistan / WHO GLASS figures; fill the `unknown` cells.
- Per-prediction TreeSHAP explainability for the V2 RandomForest model.
- Concept-drift detection and automated retraining pipeline.
- User authentication and audit logging.
- External validation on an independent hospital dataset.
- Multi-organism polymicrobial infection support.

---

## [2.1.0] — 2026-07-14  ·  V2 release (M0–M7)

> **Viva traceability.** Each item maps back to the finding it addresses. `Review §` = the
> external code-review sections; `Mn/Tn.n` = the milestone/task in [`docs/ROADMAP.md`](docs/ROADMAP.md).
> The theme of this release is *honesty*: measure the model against a real baseline, state where it
> does **not** help, calibrate what it outputs, and make locale explicit instead of implying the US
> model generalises to Pakistan.

### Added — rigorous evaluation (Review §0, §2 Tier 1 · M1)
- **`armd_model/evaluate.py`** — one seeded, patient-grouped script that regenerates every evaluation figure + `reports/metrics.json`. *(T1.1–T1.6)*
- **Per-(organism × drug) AUC** + heatmap, and the honest headline: pooled RF AUC **0.851 is below** the antibiogram baseline **0.860**, but the **within-cell median AUC is 0.650** — the RF's patient-specific re-ranking lift, which the pooled number hides. *(Review §0 — "does the ML actually beat the antibiogram?"; T1.1/T1.2)*
- **Probability calibration** — isotonic (Brier **0.168 → 0.099**); the calibrated model `rf_top3_recommender_calibrated.joblib` is now the **served default**. Isotonic is order-preserving, so Top-k rankings are unchanged. *(Review §2 — "probabilities are uncalibrated"; T1.3)*
- **Top-1 / Top-3 susceptibility hit-rate** (0.983 / 0.998 on informative contexts) as the honest substitute for coverage-rate — which is **not computable** from ARMD (no administered-drug field). *(T1.4/T1.5)*
- **Decision-curve analysis** (net benefit vs treat-all/treat-none). *(T1.6)*
- `/api/v2/model-info` now serves the `evaluation` block; the figures render on the `/model-info` dashboard.

### Added — locale-aware recommendation (M4, M6)
- **`LocaleAntibiogramService`** + `backend/antibiograms/{us_armd,pakistan}.json` — pluggable per-locale antibiograms. *(Review §3 — "don't imply the model is tuned for Pakistan")*
- **`GET /api/v2/locales`** and a `locale` field on `POST /api/v2/recommend` (default `us_armd`; contract is additive — US default unchanged). `locale=pakistan` routes to **Route A** (antibiogram-only): rank by local %-susceptible, exclude untested/unknown/below-threshold/`do_not_use` cells, **no US fallback**. Gates ceftriaxone for XDR *S.* Typhi.
- **Frontend locale toggle** (US 🇺🇸 ↔ Pakistan 🇵🇰), provenance strips (`basis`, %-susceptible, source id), struck-through excluded panel, and a research-only disclaimer on every view. *(M6)*
- **US-vs-PK contrast** on `/model-info` (`us_vs_pk_contrast`) + `reports/figures/us_vs_pk_contrast.png`. *(M6)*

### Added — dosage reframe (Review §4 · M5)
- Dosage is surfaced as a **non-validated reference** with an explicit disclaimer (`dose_disclaimer`, `dosage_model.validated=false`) rather than implying a validated dosing calculator.

### Added — thesis / examiner artifacts (M8)
- **`armd_model/make_thesis_figures.py`** — regenerates the coverage, US-vs-PK, and 3-layer architecture figures from committed artifacts only (no datasets). *(T8.1)*
- **`docs/VIVA_ONEPAGER.md`** — problem, XDR-typhoid hook, RQ, honest contributions, "do-NOT-claim" list, likely Q&A. *(T8.4)*

### Added — antibiogram clinical filter (earlier V2 work, now part of this release)
- **Antibiogram clinical filter** (`armd_model/build_antibiogram.py` → `organism_antibiotic_panel.json`) — restricts candidate antibiotics to those a lab actually tests for the organism (CLSI M39 ≥30 isolates; 85 organisms). Applied as Layer 2 of the recommendation engine so clinically nonsensical drugs can never top the ranking.

### Changed — deploy & release hygiene (M0, M7)
- `backend/Dockerfile` now bundles the calibrated model, both antibiograms, and `reports/metrics.json`; added `ANTIBIOGRAM_DIR` / `REPORTS_DIR` env vars. Health check `/health`; sized for the 512 MB Render free tier.
- **V1 (CatBoost) disabled on `version/v2_release`** — routes, services, and schemas commented out (not deleted); only `/api/v2/*` is mounted. V1 remains the live product on `main`.
- Backend deploys from `backend/Dockerfile` (Render); frontend via Vercel **Root Directory = `frontend`** — root `vercel.json` and `render.yaml` removed to fix deploy/404 conflicts.
- `README.md` + `docs/*` updated V2-primary with the honest evaluation numbers; V1 kept as a legacy note.
- **Frozen seed-42, patient-grouped (`GroupShuffleSplit` by `anon_id`) split** locked as the evaluation baseline. *(Review §2 — leakage; M0)*

### Fixed
- Pinned **`scikit-learn==1.3.2`** — newer versions fail to unpickle the shipped artifacts (`SimpleImputer has no attribute _fill_dtype`), which 500'd `/api/v2/recommend`.
- Lab values now merge correctly (`median_wbc`→`wbc_median` rename; `'Null'` parsed as NaN).
- Dosage resolution maps culture site → disease (urine→UTI, blood→Bacteremia, respiratory→Pneumonia) and never surfaces "unknown".

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
