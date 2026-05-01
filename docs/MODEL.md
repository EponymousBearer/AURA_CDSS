# Model Documentation

This document describes the machine learning pipelines for both AURA model versions: the V1 CatBoost per-antibiotic classifiers and the V2 ARMD RandomForest pipeline.

---

## Contents

**V1 — CatBoost**
- [Dataset](#dataset)
- [Preprocessing](#preprocessing)
- [Feature Schema](#feature-schema)
- [Model Design](#model-design)
- [Training Pipeline](#training-pipeline)
- [Evaluation](#evaluation)
- [Performance Summary](#performance-summary)
- [Deployment Filtering](#deployment-filtering)
- [Prediction at Inference](#prediction-at-inference)
- [Explainability](#explainability)
- [V1 Limitations](#v1-limitations)

**V2 — ARMD RandomForest**
- [V2 Dataset](#v2-dataset)
- [V2 Feature Schema](#v2-feature-schema)
- [V2 Model Design](#v2-model-design)
- [V2 Training Pipeline](#v2-training-pipeline)
- [V2 Threshold Tuning](#v2-threshold-tuning)
- [V2 Evaluation](#v2-evaluation)
- [Dosage Model](#dosage-model)
- [V2 Inference Pipeline](#v2-inference-pipeline)
- [V2 Limitations](#v2-limitations)

---

## Dataset

**Source:** Dryad Digital Repository — microbiology culture data.

**Files:**

| File | Description |
|---|---|
| `training/microbiology_cultures_demographics.csv` | Patient demographic records tied to culture events |
| `training/microbiology_cultures_microbial_resistance.csv` | Culture results with per-antibiotic sensitivity outcomes |

**Linkage:** The two files are joined on a shared culture identifier during preprocessing.

**Scale:** After cleaning and filtering, the working dataset contains **22,946 samples** covering **26 antibiotics** across **13 named organisms** plus an "Other" catch-all.

---

## Preprocessing

Implemented in `training/preprocess.py` — `DataPreprocessor` class.

### Steps

1. **Load:** Read both Dryad CSV files.
2. **Merge:** Join demographics onto resistance results.
3. **Organism normalisation:** Map uppercase Dryad labels to canonical display names.
   - `"ESCHERICHIA COLI"` → `"E. coli"`
   - `"KLEBSIELLA PNEUMONIAE"` → `"K. pneumoniae"`
   - `"PSEUDOMONAS AERUGINOSA"` → `"P. aeruginosa"`
   - *(full mapping in `preprocess.py`)*
4. **Age parsing:** Convert bucket strings to midpoint numerics.
   - `"25-34 years"` → `29.5`
5. **Synthetic feature assignment:** The source dataset does not provide kidney function or severity. These are assigned using a controlled synthetic scheme for modeling and demonstration purposes.
6. **Label encoding:** Sensitivity outcomes are binarised (susceptible = 1, resistant = 0). Intermediate categories (e.g. "intermediate") are excluded or treated as resistant.
7. **Split:** Stratified random split into:
   - `train.csv` — 70%
   - `val.csv` — 15%
   - `test.csv` — 15%
8. **Report:** Dataset statistics (organism distribution, label rates per antibiotic) are logged.

### Output files

```
training/data/train.csv
training/data/val.csv
training/data/test.csv
```

---

## Feature Schema

Five input features per sample:

| Feature | Type | Values | Source |
|---|---|---|---|
| `organism` | categorical | 13 + "Other" = 14 classes | Dryad (normalised) |
| `age` | numeric | 0–100+ (years) | Dryad (parsed from buckets) |
| `gender` | categorical | M / F | Dryad |
| `kidney_function` | categorical | normal / mild / low / severe | Synthetic |
| `severity` | categorical | low / medium / high / critical | Synthetic |

---

## Model Design

### Strategy: per-antibiotic binary classification

One `CatBoostClassifier` is trained per antibiotic to predict the binary outcome:

```
P(susceptible | organism, age, gender, kidney_function, severity)
```

This approach was chosen over multi-class / multi-label alternatives because:

- Resistance mechanisms vary independently per antibiotic; a joint model conflates them.
- Binary classification allows independent quality filtering — poor-performing antibiotics are excluded individually.
- Each model has its own SHAP attribution space, enabling per-antibiotic explainability.

### CatBoost configuration

| Hyperparameter | Value | Rationale |
|---|---|---|
| Iterations | 300 | Sufficient for 5 features; overfitting unlikely |
| Learning rate | 0.1 (default) | Standard starting point |
| Depth | 6 (default) | Balanced capacity |
| Loss function | `Logloss` | Binary classification |
| Class weights | Computed | Balances imbalanced susceptibility rates |
| Categorical features | `['organism', 'gender', 'kidney_function', 'severity']` | CatBoost native handling |
| Verbose | 0 | Suppressed during training |

CatBoost encodes categorical features using ordered target statistics (CatBoost's default), which prevents target leakage and handles high-cardinality categoricals without one-hot expansion.

---

## Training Pipeline

Implemented in `training/train.py` — `AntibioticPredictorTrainer` class.

### Flow

```
1. Load train.csv
2. For each antibiotic column:
   a. Check class distribution — skip if single class
   b. Compute class weights (inverse frequency)
   c. 5-fold cross-validation on training set
      → record CV AUC
   d. Train final model on full training set
   e. Evaluate on val.csv → AUC, F1, accuracy
   f. Flag as "included" if AUC ≥ 0.65 on validation set
3. Save all models (including excluded) to pickle:
   {
     "models": { antibiotic: CatBoostClassifier },
     "antibiotic_list": [...included only...],
     "categorical_features": [...],
     "positive_rates": { antibiotic: float }
   }
4. Save model_metadata.json with per-antibiotic metrics and status
```

### Artifacts produced

```
training/output/antibiotic_model.pkl    → copy to backend/model/
training/output/model_metadata.json     → copy to backend/model/
training/output/metrics.json            → raw training metrics
training/output/model_quality_report.json
training/output/evaluation_report.json
```

---

## Evaluation

Implemented in `training/evaluate.py`.

The evaluation script loads the trained models and the held-out `test.csv` split and computes:

- **AUC-ROC** — primary ranking metric; threshold-independent.
- **F1 Score** — harmonic mean of precision and recall at the default 0.5 threshold.
- **Accuracy** — fraction correctly classified.
- **Confusion matrix** — per antibiotic, for error analysis.

Results are written to `training/output/evaluation_report.json`.

---

## Performance Summary

Results from `training/output/metrics.json` on the validation set.

### Included antibiotics (AUC ≥ 0.65)

| Antibiotic | AUC | F1 | Accuracy |
|---|---:|---:|---:|
| Ampicillin | 0.9018 | 0.8401 | 0.8170 |
| Penicillin | 0.8980 | 0.7506 | 0.8276 |
| Erythromycin | 0.8360 | 0.6279 | 0.7386 |
| Rifampin | 0.8211 | 0.0462 | 0.7355 |
| Linezolid | 0.8164 | 0.0563 | 0.7340 |
| Vancomycin | 0.8073 | 0.2033 | 0.7514 |
| Metronidazole | 0.7965 | 0.0069 | 0.5598 |
| Meropenem | 0.7867 | 0.1271 | 0.7654 |
| Aztreonam | 0.7822 | 0.0138 | 0.6501 |
| Amikacin | 0.7802 | 0.1093 | 0.7117 |
| Nitrofurantoin | 0.7749 | 0.4391 | 0.7639 |
| Minocycline | 0.7731 | 0.0235 | 0.7209 |
| Moxifloxacin | 0.7606 | 0.3747 | 0.6263 |
| Ciprofloxacin | 0.7415 | 0.5418 | 0.7193 |
| Ertapenem | 0.7371 | 0.0485 | 0.7010 |
| Cefoxitin | 0.7321 | 0.3997 | 0.7608 |
| Clarithromycin | 0.7268 | 0.0113 | 0.7337 |
| Ceftriaxone | 0.7098 | 0.3175 | 0.5830 |
| Cefazolin | 0.7078 | 0.5324 | 0.6168 |
| Levofloxacin | 0.7030 | 0.5080 | 0.6809 |
| Cefepime | 0.6733 | 0.1500 | 0.6300 |
| Gentamicin | 0.6703 | 0.3614 | 0.6226 |
| Ceftazidime | 0.6685 | 0.2501 | 0.5427 |

**Average AUC (included):** ~0.76

### Excluded antibiotics

| Antibiotic | AUC | Reason |
|---|---:|---|
| Cefpodoxime | 0.500 | No discriminative signal (AUC = chance) |
| Colistin | 0.500 | No discriminative signal (AUC = chance) |
| Ethambutol | 0.000 | Degenerate — single class in training data |

### Interpretation notes

- **High AUC, low F1** (e.g. Rifampin AUC 0.82, F1 0.05): the antibiotic is rarely susceptible in the dataset (class imbalance). AUC is still informative because it measures rank discrimination regardless of threshold.
- **Moderate AUC** (0.65–0.75): predictions carry meaningful signal but with wider uncertainty. The UI surfaces probabilities rather than binary decisions so clinicians can apply their own threshold.

---

## Deployment Filtering

At startup, `PredictionService` loads the pickle and exposes only the models whose antibiotic name appears in `antibiotic_list`. This list is populated during training by excluding any antibiotic that fails the AUC ≥ 0.65 threshold or has a degenerate class distribution.

The excluded models are still stored in the pickle (for reference) but are never called at inference time.

---

## Prediction at Inference

### Step 1 — Feature DataFrame

```python
df = pd.DataFrame([{
    "organism":         normalise(organism),
    "age":              age,
    "gender":           gender,
    "kidney_function":  kidney_function,
    "severity":         severity
}])
```

### Step 2 — Raw probability

For each antibiotic in `antibiotic_list`:

```python
raw_prob = model.predict_proba(df)[0][1]   # P(susceptible)
```

### Step 3 — Baseline correction

```python
adjusted = raw_prob - positive_rates[antibiotic]
```

`positive_rates[antibiotic]` is the mean susceptibility rate in the training set. Subtracting it produces an *excess susceptibility* score that highlights antibiotics that perform *better than their baseline* for this specific patient.

### Step 4 — Organism compatibility weighting

A clinical compatibility map assigns a multiplier per (organism, antibiotic) pair. For example:

- Vancomycin against Gram-negative organisms receives a penalty (low compatibility).
- Aztreonam against Gram-positive organisms receives a penalty.

This prevents the ranker from recommending antibiotics that are intrinsically inactive against the target organism regardless of the model's raw score.

### Step 5 — Ranking

The top-k (default 3) antibiotics by adjusted + weighted score are returned.

---

## Explainability

AURA uses CatBoost's native SHAP implementation to produce per-prediction feature importances.

```python
shap_values = model.get_feature_importance(
    Pool(df, cat_features=categorical_features),
    type="ShapValues"
)
feature_importance = dict(zip(feature_names, shap_values[0][:-1]))
```

The returned dictionary maps each feature name to its SHAP value:

- **Positive value:** the feature pushed the prediction toward susceptible.
- **Negative value:** the feature pushed the prediction toward resistant.
- **Magnitude:** the strength of the contribution relative to the model's base rate.

The frontend renders these values in an expandable modal on each `ResultCard`, sorted by absolute importance.

---

## V1 Limitations

1. **Synthetic features:** `kidney_function` and `severity` are not from real clinical records. They demonstrate the system's architecture but reduce clinical validity.
2. **Training corpus scope:** The Dryad dataset covers a specific time period, geography, and hospital type. Local resistance patterns vary.
3. **No time dimension:** Resistance rates change over time. The model is a static snapshot and will require retraining as patterns shift.
4. **Calibration:** `predict_proba` outputs from CatBoost are not calibrated. The displayed percentages are discriminative scores, not clinical probabilities in the strict sense.
5. **No infection-site modelling:** The same organism may have different susceptibility profiles in a UTI vs. bloodstream infection; this model does not distinguish.
6. **Label quality:** Some sensitivity outcomes in the Dryad source use intermediate categories that are handled conservatively (treated as resistant), which may underestimate true susceptibility rates.

---

---

# V2 — ARMD RandomForest Pipeline

`armd_model/train_armd.py` · `armd_model/train_dosage.py` · `backend/app/services/armd_predictor.py`

---

## V2 Dataset

**Source:** ARMD (Antimicrobial Resistance Management Dataset) — six linked clinical CSV files derived from hospital microbiology records, plus one dosage reference file.

Download from: [Google Drive](https://drive.google.com/drive/folders/1agc1hXlVinXAPM-7E8RFfAFopKVrIota?usp=sharing) → place in `datasets/`.

| File | Description |
|---|---|
| `microbiology_cultures_cohort.csv` | Core culture events: culture ID, organism, antibiotic, susceptibility outcome |
| `microbiology_cultures_demographics.csv` | Patient demographics: age, gender per culture event |
| `microbiology_cultures_labs.csv` | Lab values at time of culture: WBC, creatinine, lactate, procalcitonin |
| `microbiology_cultures_antibiotic_class_exposure.csv` | Prior antibiotic class exposure history per patient |
| `microbiology_culture_prior_infecting_organism.csv` | Prior infecting organism history per patient |
| `microbiology_cultures_ward_info.csv` | Ward / unit at time of culture (ICU, ER, inpatient) |
| `d_dose.csv` | Clinical dosage reference: antibiotic × organism → dose range, route |

All files are joined on a shared culture identifier during preprocessing.

---

## V2 Feature Schema

42 model features across six groups:

| Group | Features | Type |
|---|---|---|
| Core | `culture_description`, `organism`, `antibiotic` | categorical |
| Demographics | `age`, `gender` | numeric / categorical |
| Labs | `wbc_median`, `cr_median`, `lactate_median`, `procalcitonin_median` | numeric |
| Ward | `ward__icu`, `ward__er`, `ward__ip` | binary |
| Prior ABX class | `prior_abxclass__<class>` (one per class) | binary |
| Prior organism | `prior_org__<organism>` (one per organism) | binary |

**Inference note:** Prior ABX class and prior organism features default to `0` at inference time because the V2 UI does not yet capture patient history. This reduces recall for patients with complex prior exposures but does not affect the core susceptibility signal from organism and labs.

---

## V2 Model Design

**Strategy: single pipeline with antibiotic as a feature**

One `RandomForestClassifier` is trained on all `(culture, organism, antibiotic)` triplets simultaneously. Antibiotic identity is injected as a categorical feature rather than training a separate model per antibiotic.

```
Input row:  culture_description | organism | antibiotic | age | gender | wbc | cr | ... | prior_org__*
Label:      susceptible (1) / resistant (0)
```

This design is preferred over per-antibiotic classifiers for V2 because:
- Shared representations — the model learns cross-antibiotic resistance patterns (e.g. beta-lactam class effects).
- Scalability — adding new antibiotics requires only retraining, not a new model object.
- Dosage integration — the same feature space is reused for the dosage fallback models.

**RandomForest configuration:**

| Hyperparameter | Value | Rationale |
|---|---|---|
| `n_estimators` | 300 | Stable variance reduction across 42 features |
| `max_depth` | 18 | Captures complex lab × organism × antibiotic interactions |
| `class_weight` | `balanced_subsample` | Handles susceptibility imbalance independently per tree |
| `min_samples_leaf` | 5 | Prevents overfitting on rare organism/antibiotic combinations |
| `random_state` | 42 | Reproducibility |

---

## V2 Training Pipeline

Implemented in `armd_model/train_armd.py`.

```
1.  Load all 6 ARMD CSV files from datasets/
2.  Merge on culture_id
3.  Feature engineering
      a. Aggregate lab values → median per culture event
      b. One-hot encode prior antibiotic classes   → prior_abxclass__* binary columns
      c. One-hot encode prior organisms            → prior_org__* binary columns
      d. Map ward string → binary flags            → ward__icu / ward__er / ward__ip
4.  Label: susceptibility (1 = susceptible, 0 = resistant / intermediate)
5.  Stratified split: 70 % train / 15 % val / 15 % test
6.  Train RandomForestClassifier on train split
7.  Tune decision threshold on val split (see below)
8.  Evaluate final model on held-out test split
9.  Save all artifacts to armd_model/artifacts/
```

**Artifacts produced:**

| Artifact | Description |
|---|---|
| `rf_top3_recommender_optimized.joblib` | Trained RF pipeline (preprocessor + classifier) |
| `feature_cols.joblib` | Ordered feature column list |
| `selected_antibiotics.joblib` | 32 antibiotic names |
| `best_threshold.joblib` | Tuned decision threshold |
| `feature_importances.joblib` | Per-feature importance scores |
| `split_test_summary.joblib` | Held-out test metrics dict |
| `metadata_optimized.json` | Training metadata (date, hyperparameters, metrics) |

---

## V2 Threshold Tuning

The model uses a **recall-first** threshold policy:

1. Score all validation samples with `predict_proba`.
2. Sweep candidate thresholds from 0.01 to 0.99 (step 0.01).
3. For each threshold compute recall and precision on the validation set.
4. Select the lowest threshold where **precision ≥ 0.85**, maximising recall.

**Result:** tuned threshold = **0.23**

This prioritises sensitivity (not missing a susceptible antibiotic) over specificity, which is appropriate for a recommendation system where a false negative (missing an effective drug) is more harmful than a false positive (suggesting a drug that is checked further by the clinician).

---

## V2 Evaluation

Evaluated on the held-out test split (15 % of data, never seen during training or threshold tuning) at threshold 0.23:

| Metric | Score |
|---|---:|
| ROC AUC | 84.5 % |
| F1 Score | 91.8 % |
| Recall | 99.5 % |
| Precision | 85.2 % |
| Accuracy | 85.2 % |

**Interpretation:**
- **High recall (99.5 %):** the model rarely misses a susceptible antibiotic, consistent with the recall-first tuning objective.
- **ROC AUC 84.5 %:** strong rank discrimination across 32 antibiotics and multiple organisms.
- **Precision 85.2 %:** ~15 % of recommended antibiotics may not be susceptible in vitro; clinicians are expected to confirm with culture results.

---

## Dosage Model

Implemented in `armd_model/train_dosage.py` and `backend/app/services/dosage_service.py`.

Uses a **three-tier fallback chain** for every recommended antibiotic:

```
Tier 1 — Exact lookup
  Query dose_route_lookup.csv for (antibiotic, organism) pair.
  If found → return exact dose range and route.
  Source: 45 k-row lookup table built from d_dose.csv.

Tier 2 — RF fallback
  If (antibiotic, organism) not in lookup:
  → dose_model_hybrid.pkl   predicts dose range
  → route_model_hybrid.pkl  predicts IV / PO route
  Features: antibiotic and organism (label-encoded).

Tier 3 — Rule engine
  If RF artifacts unavailable:
  → V1 DosingRuleEngine (20+ antibiotic entries, 4-tier renal adjustment).
```

**Artifacts produced by `train_dosage.py`:**

| Artifact | Description |
|---|---|
| `dose_route_lookup.csv` | Exact (antibiotic, organism) → dose range + route lookup |
| `dose_model_hybrid.pkl` | RF fallback for dose range |
| `route_model_hybrid.pkl` | RF fallback for IV/PO route |

The `dose_source` field in the API response reports which tier was used (`lookup`, `model`, or `rules`), enabling downstream audit of recommendation provenance.

---

## V2 Inference Pipeline

At inference time, for a single patient request:

```python
# 1. Build one feature row per antibiotic (32 total)
rows = []
for ab in selected_antibiotics:
    row = {
        "culture_description": request.culture_description,
        "organism":            request.organism,
        "antibiotic":          ab,
        "age":                 request.age,
        "gender":              request.gender,
        "wbc_median":          request.wbc,
        "cr_median":           request.cr,
        "lactate_median":      request.lactate,
        "procalcitonin_median":request.procalcitonin,
        "ward__icu":           1 if request.ward == "icu" else 0,
        "ward__er":            1 if request.ward == "er"  else 0,
        "ward__ip":            1 if request.ward == "general" else 0,
        # prior history features default to 0
    }
    rows.append(row)

# 2. Score all 32 rows through the RF pipeline
df = pd.DataFrame(rows)[feature_cols]
probs = pipeline.predict_proba(df)[:, 1]

# 3. Rank by probability, return top 3
ranked = sorted(zip(selected_antibiotics, probs), key=lambda x: -x[1])
top3   = ranked[:3]

# 4. Attach dosage via DosageService (3-tier fallback)
results = [dosage_service.get_dose(ab, organism) for ab, _ in top3]
```

The `all_predictions` field in the response contains the full ranked list of all 32 antibiotics, which is used by the `ResistanceChart` component in the frontend.

---

## V2 Limitations

1. **Prior history defaults to zero:** `prior_abxclass__*` and `prior_org__*` features are set to 0 at inference because the UI does not capture patient history. Patients with relevant prior exposure may receive suboptimal rankings.
2. **Uncalibrated probabilities:** `predict_proba` from RandomForest tends to be over-confident near 0 and 1. Outputs are discriminative scores, not calibrated clinical probabilities.
3. **No per-prediction explainability:** Only global feature importances are available. Per-prediction TreeSHAP is planned but not yet implemented.
4. **Single-institution data:** The ARMD dataset reflects the resistance patterns of a specific hospital population. Generalisability to other institutions requires external validation.
5. **Static snapshot:** The model does not incorporate temporal trends. Resistance patterns evolve and the model will require periodic retraining.
6. **32-antibiotic scope:** Antibiotics not present in the ARMD training data cannot be scored; the dosage fallback chain handles unseen combinations but prediction confidence is lower.
