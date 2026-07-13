# API Reference

Base URL (local development): `http://localhost:8000`
Interactive docs (Swagger): `http://localhost:8000/docs` · ReDoc: `http://localhost:8000/redoc`

All endpoints return JSON. Every response includes an `X-Request-ID` header (UUID) for tracing. Error responses follow the [Error Schema](#error-schema).

> **Branch note:** On `version/v2_release` the backend mounts **only** the V2 router (`/api/v2/*`) plus `/` and `/health`. The V1 (`/api/v1/*`) endpoints are commented out here and live on the `main` branch — they are listed under [V1 legacy endpoints](#v1-legacy-endpoints-main-branch) for reference only.

---

## Contents

**Active (this branch)**
- [GET /](#get-)
- [GET /health](#get-health)
- [GET /api/v2/organisms](#get-apiv2organisms)
- [POST /api/v2/recommend](#post-apiv2recommend)
- [GET /api/v2/model-info](#get-apiv2model-info)
- [Error Schema](#error-schema)

**Legacy (`main` branch)**
- [V1 legacy endpoints](#v1-legacy-endpoints-main-branch)

---

## GET /

Service identity and version.

```json
{
  "name": "Antibiotic AI CDSS API",
  "version": "1.0.0",
  "status": "operational",
  "docs_url": "/docs",
  "endpoints": {
    "recommend": "/api/v2/recommend"
  }
}
```

---

## GET /health

Liveness probe. Returns `200` when the service is up. Used by the Docker healthcheck and Render.

```json
{ "status": "healthy", "service": "antibiotic-ai-cdss" }
```

---

## GET /api/v2/organisms

Returns ARMD culture sites and valid organism options. The organism list is derived at runtime from `datasets/microbiology_cultures_cohort.csv` (falls back to a small built-in list if the cohort file is absent). Pass `culture_description` to get the organisms for one site.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `culture_description` | string | No | Culture site; if provided, returns that site's organism list. |

**Example — all sites**

```
GET /api/v2/organisms
```
```json
{
  "culture_sites": ["blood", "respiratory", "urine"],
  "organisms_by_culture": {
    "urine": ["escherichia coli", "klebsiella pneumoniae", "proteus mirabilis", "other"],
    "blood": ["escherichia coli", "staphylococcus aureus", "other"]
  }
}
```

**Example — one site**

```
GET /api/v2/organisms?culture_description=urine
```
```json
{
  "culture_sites": ["blood", "respiratory", "urine"],
  "culture_description": "urine",
  "organisms": ["escherichia coli", "klebsiella pneumoniae", "other"]
}
```

---

## POST /api/v2/recommend

Core endpoint. Scores candidate antibiotics for susceptibility with the ARMD RandomForest, filters them through the organism's antibiogram panel, ranks by probability, returns the top 3 enriched with dose range + route, plus the full ranked list. See the [3-layer engine](MODEL.md#v2-inference--the-3-layer-engine).

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `culture_description` | string (1–200) | Yes | Culture site; must be a supported site. |
| `organism` | string (1–200) | Yes | Infecting organism; must be valid for the site (or `other`). Lowercased internally. |
| `age` | integer (0–150) | Yes | Patient age in years. |
| `gender` | string | Yes | `male` or `female`. |
| `wbc` | float ≥ 0 | No | WBC (×10³/μL). Missing → imputed. |
| `cr` | float ≥ 0 | No | Creatinine (mg/dL). |
| `lactate` | float ≥ 0 | No | Lactate (mmol/L). |
| `procalcitonin` | float ≥ 0 | No | Procalcitonin (ng/mL). |
| `ward` | enum | No | `general` (→ IP), `icu`, `er`. Default `general`. |

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

### Response 200

| Field | Type | Description |
|---|---|---|
| `recommendations` | array[ARMDResult] | Top 3 antibiotics (post-antibiogram-filter). |
| `patient_factors` | object | Echo of the submitted inputs. |
| `culture_description` | string | Culture site used for the dosage lookup. |
| `all_predictions` | array | Every scored antibiotic, sorted by probability descending. |

**ARMDResult**

| Field | Type | Description |
|---|---|---|
| `antibiotic` | string | Antibiotic name. |
| `probability` | float (0–1) | `P(susceptible)`. |
| `dose_range` | string | Recommended dose range. |
| `route` | string | `IV` / `PO` / `IM`. |
| `dose_source` | string | `lookup` / `model` / `fallback`. |

```json
{
  "recommendations": [
    { "antibiotic": "meropenem", "probability": 0.871, "dose_range": "500-1000 mg", "route": "IV", "dose_source": "lookup" },
    { "antibiotic": "ertapenem", "probability": 0.842, "dose_range": "1000 mg",     "route": "IV", "dose_source": "lookup" },
    { "antibiotic": "amikacin",  "probability": 0.795, "dose_range": "15-20 mg/kg",  "route": "IV", "dose_source": "fallback" }
  ],
  "patient_factors": {
    "culture_description": "urine", "organism": "klebsiella pneumoniae",
    "age": 45, "gender": "female", "wbc": 12.5, "cr": 1.2,
    "lactate": 1.8, "procalcitonin": 2.5, "ward": "er"
  },
  "culture_description": "urine",
  "all_predictions": [
    { "antibiotic": "meropenem", "probability": 0.871 },
    { "antibiotic": "ertapenem", "probability": 0.842 }
  ]
}
```

### Error responses

| Code | Meaning |
|---|---|
| `422` | Unsupported culture site, or organism invalid for the chosen site, or Pydantic validation failure. |
| `503` | ARMD model not loaded — artifacts missing (run `train_armd.py`). |
| `500` | Server error during inference. |

---

## GET /api/v2/model-info

Returns the ARMD model inventory, feature groups, held-out test metrics, top feature importances, and dosage-model status. Values below are from the shipped artifacts.

```json
{
  "model_type": "RandomForest (ARMD)",
  "n_antibiotics": 32,
  "n_features": 46,
  "best_threshold": 0.5,
  "available": true,
  "antibiotics": ["amikacin", "ampicillin", "aztreonam", "..."],
  "feature_groups": {
    "categorical": ["culture_description", "organism", "antibiotic", "gender"],
    "numeric": ["age", "wbc_median", "cr_median", "lactate_median", "procalcitonin_median"],
    "binary": ["prior_abxclass__aminoglycoside", "prior_org__escherichia", "ward__icu", "..."]
  },
  "test_summary": [
    {
      "split": "test",
      "threshold": 0.5,
      "accuracy": 0.787611,
      "balanced_accuracy": 0.774249,
      "precision_1": 0.941971,
      "recall_1": 0.794255,
      "f1_1": 0.861829,
      "roc_auc": 0.851043
    }
  ],
  "top_feature_importances": [
    { "feature": "cat__antibiotic_ampicillin", "importance": 0.194638 },
    { "feature": "cat__antibiotic_tetracycline", "importance": 0.089808 },
    { "feature": "cat__antibiotic_meropenem", "importance": 0.071357 }
  ],
  "dosage_model": {
    "model_type": "Hybrid lookup + RandomForest fallback",
    "available": true,
    "lookup_entries": 840,
    "fallback_antibiotics": 32
  }
}
```

> The response also nests `models.recommendation` and `models.dosage` with the same payloads.

---

## Error Schema

```json
{
  "error":   "string — error type identifier",
  "detail":  "string — human-readable description",
  "suggestion": "string (optional) — remediation hint"
}
```

| Code | Meaning |
|---|---|
| 200 | Success |
| 422 | Unprocessable entity — validation failure / unsupported culture site or organism |
| 500 | Internal server error |
| 503 | Model not loaded (artifacts missing) |

---

## V1 legacy endpoints (`main` branch)

> **Not available on this branch** — the V1 router is commented out and never mounted (`main.py`). These exist on `main` for the CatBoost product. Listed here for reference only.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/organisms` | 14 supported organisms (enum). |
| `GET` | `/api/v1/antibiotics` | Antibiotics the loaded CatBoost model can score. |
| `POST` | `/api/v1/recommend` | Top-3 recommendations + rule-based dosing (dose/route/frequency/duration/notes). Inputs: `organism`, `age`, `gender`, `kidney_function`, `severity`. |
| `POST` / `GET` | `/api/v1/explain` | SHAP feature importance for one antibiotic prediction. |
| `GET` | `/api/v1/model-info` | Per-antibiotic AUC/F1/accuracy table + training metadata. |

See [`MODEL.md`](MODEL.md#v1-legacy--catboost-on-main) for the V1 model details and metrics.
