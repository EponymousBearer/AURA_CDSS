# API Reference

Base URL (local development): `http://localhost:8000`
Interactive docs (Swagger): `http://localhost:8000/docs`
ReDoc: `http://localhost:8000/redoc`

All endpoints return JSON. All error responses follow the [Error Schema](#error-schema).
Every response includes an `X-Request-ID` header with a UUID for tracing.

---

## Contents

- [Root](#get-)
- [Health Check](#get-health)
- [Organisms](#get-apiv1organisms)
- [Antibiotics](#get-apiv1antibiotics)
- [Recommend](#post-apiv1recommend)
- [Explain (POST)](#post-apiv1explain)
- [Explain (GET)](#get-apiv1explain)
- [V1 Model Info](#get-apiv1model-info)
- [V2 Model Info](#get-apiv2model-info)
- [Supported Organisms](#supported-organisms)
- [Enum Reference](#enum-reference)
- [Error Schema](#error-schema)

---

## GET /

Returns service identity and version information.

**Response 200**

```json
{
  "name": "Antibiotic AI CDSS API",
  "version": "1.0.0",
  "status": "operational",
  "docs_url": "/docs",
  "endpoints": {
    "recommend": "/api/v1/recommend"
  }
}
```

---

## GET /health

Liveness probe. Returns `200` when the service is up. Used by Docker healthcheck and Render.

**Response 200**

```json
{
  "status": "healthy",
  "service": "antibiotic-ai-cdss"
}
```

---

## GET /api/v1/organisms

Returns the list of bacterial organisms the system accepts.

**Response 200**

```json
{
  "organisms": [
    { "code": "E. coli",                       "name": "E. coli" },
    { "code": "K. pneumoniae",                 "name": "K. pneumoniae" },
    { "code": "P. aeruginosa",                 "name": "P. aeruginosa" },
    { "code": "A. baumannii",                  "name": "A. baumannii" },
    { "code": "S. aureus",                     "name": "S. aureus" },
    { "code": "E. faecium",                    "name": "E. faecium" },
    { "code": "S. pneumoniae",                 "name": "S. pneumoniae" },
    { "code": "Enterococcus spp",              "name": "Enterococcus spp" },
    { "code": "COAG NEGATIVE STAPHYLOCOCCUS",  "name": "COAG NEGATIVE STAPHYLOCOCCUS" },
    { "code": "KLEBSIELLA OXYTOCA",            "name": "KLEBSIELLA OXYTOCA" },
    { "code": "PROTEUS MIRABILIS",             "name": "PROTEUS MIRABILIS" },
    { "code": "STAPHYLOCOCCUS EPIDERMIDIS",    "name": "STAPHYLOCOCCUS EPIDERMIDIS" },
    { "code": "ENTEROCOCCUS FAECALIS",         "name": "ENTEROCOCCUS FAECALIS" },
    { "code": "Other",                         "name": "Other" }
  ]
}
```

---

## GET /api/v1/antibiotics

Returns the list of antibiotics the loaded model can score.

**Response 200**

```json
{
  "antibiotics": [
    "Ampicillin",
    "Penicillin",
    "Erythromycin",
    "..."
  ]
}
```

**Response 500** — model not loaded or list unavailable.

---

## POST /api/v1/recommend

Core endpoint. Scores all antibiotics for susceptibility, ranks them with baseline-correction and organism-compatibility weighting, applies rule-based dosing, and returns the top 3 recommendations plus the full probability list.

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `organism` | `string` (enum) | Yes | Bacterial organism — see [Supported Organisms](#supported-organisms) |
| `age` | `integer` | Yes | Patient age in years (0–150) |
| `gender` | `string` (enum) | Yes | `M` or `F` |
| `kidney_function` | `string` (enum) | Yes | `normal` \| `mild` \| `low` \| `severe` |
| `severity` | `string` (enum) | Yes | `low` \| `medium` \| `high` \| `critical` |

```json
{
  "organism": "E. coli",
  "age": 65,
  "gender": "F",
  "kidney_function": "normal",
  "severity": "medium"
}
```

### Response 200

| Field | Type | Description |
|---|---|---|
| `organism` | `string` | Echo of requested organism |
| `patient_factors` | `object` | Echo of age, gender, kidney_function, severity |
| `recommendations` | `array[AntibioticResult]` | Top 3 antibiotics (0–3 items) |
| `all_predictions` | `array[AntibioticPrediction]` | All antibiotics sorted by probability descending |

**AntibioticResult**

| Field | Type | Description |
|---|---|---|
| `antibiotic` | `string` | Antibiotic name |
| `probability` | `float` (0–1) | Adjusted susceptibility probability |
| `dose` | `string` | Recommended dose (renal-adjusted if applicable) |
| `route` | `string` | `IV` or `PO` |
| `frequency` | `string` | Dosing interval |
| `duration` | `string` | Treatment duration (severity-extended if applicable) |
| `clinical_notes` | `string` | Guidance text |

```json
{
  "organism": "E. coli",
  "patient_factors": {
    "age": 65,
    "gender": "F",
    "kidney_function": "normal",
    "severity": "medium"
  },
  "recommendations": [
    {
      "antibiotic": "Ampicillin",
      "probability": 0.910,
      "dose": "1-2 g",
      "route": "PO",
      "frequency": "Every 4-6 hours",
      "duration": "7-14 days",
      "clinical_notes": "Narrow spectrum for susceptible organisms"
    },
    {
      "antibiotic": "Ceftriaxone",
      "probability": 0.874,
      "dose": "1-2 g",
      "route": "PO",
      "frequency": "Every 24 hours",
      "duration": "7-14 days",
      "clinical_notes": "First-line therapy for many Gram-negative infections"
    },
    {
      "antibiotic": "Ciprofloxacin",
      "probability": 0.821,
      "dose": "400 mg",
      "route": "PO",
      "frequency": "Every 12 hours",
      "duration": "7-14 days",
      "clinical_notes": "Excellent Gram-negative coverage including Pseudomonas"
    }
  ],
  "all_predictions": [
    { "antibiotic": "Ampicillin",    "probability": 0.910 },
    { "antibiotic": "Ceftriaxone",   "probability": 0.874 },
    { "antibiotic": "Ciprofloxacin", "probability": 0.821 },
    { "antibiotic": "Meropenem",     "probability": 0.612 }
  ]
}
```

### Response 400

Age out of range (< 0 or > 150).

### Response 422

Pydantic validation error — invalid enum value or missing field.

### Response 500

Model inference failure.

---

## POST /api/v1/explain

Returns SHAP-based feature importance for a single antibiotic prediction. The feature importance values indicate how much each patient factor contributed to the susceptibility score for that antibiotic.

### Request body

Same fields as `/recommend` plus:

| Field | Type | Required | Description |
|---|---|---|---|
| `antibiotic` | `string` | Yes | Antibiotic name to explain (must be in the loaded model) |

```json
{
  "organism": "E. coli",
  "age": 65,
  "gender": "F",
  "kidney_function": "normal",
  "severity": "medium",
  "antibiotic": "Ceftriaxone"
}
```

### Response 200

Dictionary mapping feature name → SHAP importance value.
Positive values push the prediction toward susceptibility; negative values toward resistance.

```json
{
  "organism": 0.312,
  "age":       0.048,
  "gender":   -0.011,
  "kidney_function": 0.002,
  "severity":  0.019
}
```

### Response 404

Antibiotic not found in the loaded model set.

### Response 400 / 422 / 500

Same as `/recommend`.

---

## GET /api/v1/explain

Same semantics as `POST /api/v1/explain` but accepts all parameters as query strings. Used by the frontend `ResultCard` component.

### Query parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `organism` | `string` | Yes | Bacterial organism |
| `age` | `integer` | Yes | Patient age |
| `gender` | `string` | Yes | `M` or `F` |
| `kidney_function` | `string` | Yes | Renal function tier |
| `severity` | `string` | Yes | Infection severity |
| `antibiotic` | `string` | Yes | Antibiotic to explain |

**Example request**

```
GET /api/v1/explain?organism=E.+coli&age=65&gender=F&kidney_function=normal&severity=medium&antibiotic=Ceftriaxone
```

**Response 200** — same shape as POST `/explain`.

---

## GET /api/v1/model-info

Returns model inventory, per-antibiotic quality metrics, and training metadata.

### Response 200

```json
{
  "trained_at": "2024-11-15T14:32:10.123456",
  "n_antibiotics": 23,
  "training_samples": 22946,
  "antibiotics": [
    {
      "name": "Ampicillin",
      "auc": 0.9018,
      "f1": 0.8401,
      "accuracy": 0.8170,
      "status": "included"
    },
    {
      "name": "Cefpodoxime",
      "auc": 0.5000,
      "f1": 0.0000,
      "accuracy": 0.9808,
      "status": "excluded"
    }
  ]
}
```

---

## GET /api/v2/model-info

Returns the current ARMD model inventory, held-out test results, feature importances, and dosage model status.

### Response 200

```json
{
  "model_type": "RandomForest (ARMD)",
  "n_antibiotics": 32,
  "n_features": 42,
  "best_threshold": 0.23,
  "available": true,
  "antibiotics": ["amikacin", "ampicillin", "aztreonam"],
  "feature_groups": {
    "categorical": ["culture_description", "organism", "antibiotic", "gender"],
    "numeric": ["age"],
    "binary": ["prior_abxclass__aminoglycoside", "ward__icu"]
  },
  "test_summary": [
    {
      "split": "test",
      "threshold": 0.23,
      "accuracy": 0.851803,
      "balanced_accuracy": 0.562383,
      "precision_1": 0.852302,
      "recall_1": 0.994838,
      "f1_1": 0.918071,
      "roc_auc": 0.844789
    }
  ],
  "top_feature_importances": [
    { "feature": "antibiotic", "importance": 0.518831 }
  ],
  "dosage_model": {
    "model_type": "Hybrid lookup + RandomForest fallback",
    "available": true,
    "lookup_entries": 840,
    "fallback_antibiotics": 32
  }
}
```

---

## GET /api/v2/organisms

Returns ARMD culture sites and valid organism options. Pass `culture_description` to get the organism list for one culture site.

**Example request**

```
GET /api/v2/organisms?culture_description=urine
```

**Response 200**

```json
{
  "culture_sites": ["blood", "respiratory", "urine"],
  "culture_description": "urine",
  "organisms": ["escherichia coli", "klebsiella pneumoniae", "other"]
}
```

---

## Supported Organisms

| Code (API value) | Common name |
|---|---|
| `E. coli` | Escherichia coli |
| `K. pneumoniae` | Klebsiella pneumoniae |
| `P. aeruginosa` | Pseudomonas aeruginosa |
| `A. baumannii` | Acinetobacter baumannii |
| `S. aureus` | Staphylococcus aureus |
| `E. faecium` | Enterococcus faecium |
| `S. pneumoniae` | Streptococcus pneumoniae |
| `Enterococcus spp` | Enterococcus species |
| `COAG NEGATIVE STAPHYLOCOCCUS` | Coagulase-negative staphylococci |
| `KLEBSIELLA OXYTOCA` | Klebsiella oxytoca |
| `PROTEUS MIRABILIS` | Proteus mirabilis |
| `STAPHYLOCOCCUS EPIDERMIDIS` | Staphylococcus epidermidis |
| `ENTEROCOCCUS FAECALIS` | Enterococcus faecalis |
| `Other` | Other / unspecified organism |

---

## Enum Reference

### `kidney_function`

| Value | Clinical interpretation |
|---|---|
| `normal` | CrCl ≥ 60 mL/min (no dose adjustment) |
| `mild` | CrCl 45–59 mL/min (modest dose adjustment) |
| `low` | CrCl 15–44 mL/min (significant dose adjustment) |
| `severe` | CrCl < 15 mL/min or dialysis (maximum adjustment) |

### `severity`

| Value | Clinical context |
|---|---|
| `low` | Outpatient, mild symptoms, tolerating oral |
| `medium` | Inpatient, systemic signs, IV appropriate |
| `high` | Severe sepsis, ICU-adjacent, IV required |
| `critical` | Septic shock / ICU, escalate therapy, extended duration |

---

## Error Schema

```json
{
  "error": "string — error type identifier",
  "detail": "string — human-readable description",
  "suggestion": "string (optional) — remediation hint"
}
```

### HTTP status codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 400 | Client error — invalid age range |
| 404 | Not found — antibiotic not in model |
| 422 | Unprocessable entity — Pydantic validation failure |
| 500 | Internal server error — model or rule engine failure |
