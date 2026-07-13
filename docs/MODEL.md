# Model Documentation

This document describes the machine-learning pipelines for AURA. The **active** system on this branch (`version/v2_release`) is the **V2 ARMD RandomForest** recommender plus the hybrid dosage model. The **V1 CatBoost** pipeline is the separate product line that lives on `main`; it is summarized here as a [legacy note](#v1-legacy--catboost-on-main) and is commented out on this branch.

All numbers below are verified against the shipped artifacts in `armd_model/artifacts/`.

---

## Contents

**V2 — ARMD RandomForest (active)**
- [V2 Dataset](#v2-dataset)
- [V2 Data Pipeline & Feature Engineering](#v2-data-pipeline--feature-engineering)
- [V2 Feature Schema](#v2-feature-schema)
- [V2 Model Design](#v2-model-design)
- [V2 Threshold Tuning](#v2-threshold-tuning)
- [V2 Evaluation](#v2-evaluation)
- [The Antibiogram Filter](#the-antibiogram-filter)
- [V2 Inference — the 3-layer engine](#v2-inference--the-3-layer-engine)
- [Dosage Model](#dosage-model)
- [V2 Limitations](#v2-limitations)

**V1 — CatBoost (legacy, `main`)**
- [V1 legacy note](#v1-legacy--catboost-on-main)

---

# V2 — ARMD RandomForest Pipeline

`armd_model/train_armd.py` · `armd_model/build_antibiogram.py` · `armd_model/train_dosage.py` · `backend/app/services/armd_predictor.py` · `backend/app/services/dosage_service.py`

---

## V2 Dataset

**Source:** ARMD (Antimicrobial Resistance Microbiology Dataset) — six linked clinical CSV files derived from hospital microbiology records, plus one dosage reference file.

Download from: [Google Drive](https://drive.google.com/drive/folders/1agc1hXlVinXAPM-7E8RFfAFopKVrIota?usp=sharing) → place in `datasets/`.

| File | Role |
|---|---|
| `microbiology_cultures_cohort.csv` | **Core.** One row per (culture × antibiotic): `organism`, `culture_description`, `antibiotic`, `susceptibility`, `was_positive`. Source of the label, the antibiogram, and the runtime organism dropdown. |
| `microbiology_cultures_demographics.csv` | `age` (banded), `gender`. |
| `microbiology_cultures_labs.csv` | Per-period medians: `median_wbc`, `median_cr`, `median_lactate`, `median_procalcitonin`. |
| `microbiology_cultures_antibiotic_class_exposure.csv` | Prior antibiotic-**class** exposure → `prior_abxclass__*`. |
| `microbiology_culture_prior_infecting_organism.csv` | Prior infecting organisms → `prior_org__*`. |
| `microbiology_cultures_ward_info.csv` | Ward flags → `ward__icu` / `ward__er` / `ward__ip`. |
| `d_dose.csv` | Dosing reference (dose ranges, routes, age bands, disease) → the dosage model. |

All tables are joined on the patient key **`anon_id`** (not a per-culture id).

**Label:** `susceptibility` → binary target — **`Susceptible → 1`**, **`Resistant → 0`** (anything else dropped). Only positive cultures (`was_positive ∈ {1,true,t,yes,y,positive}`) and the 32 selected antibiotics are kept.

---

## V2 Data Pipeline & Feature Engineering

Implemented in `armd_model/train_armd.py` as an 8-step pipeline.

1. **Load & filter core cohort** — positive cultures only; normalize antibiotic names (lowercase, strip, `_`/`-`→space); keep the 32 selected antibiotics; map label; drop rows missing `anon_id`/`organism`/`culture_description`/`antibiotic`/`target`.
2. **Demographics** — `age` is stored as **bands** and mapped to a representative midpoint by `convert_age_to_numeric()` (e.g. `65-74 years → 69.5`, `85+ years → 90`, `less than 1 year → 0.5`, `unknown → NaN`).
3. **Labs** — the file stores medians as `median_wbc`/`median_cr`/`median_lactate`/`median_procalcitonin` and uses the literal string `'Null'` for missing values. These are read with `na_values=['Null']`, **renamed** to the model's `*_median` names (a real bug fixed: without the rename the labs never merged), and collapsed to one row per patient by averaging available medians.
4. **Prior antibiotic-class exposure (chunked)** — read in 150 k-row chunks; aggregate each patient's set of prior antibiotic classes → `prior_abxclass__*` binary flags.
5. **Prior infecting organisms (chunked, width-limited)** — same chunked approach; keep the top-50 organisms by frequency → `prior_org__*` flags.
6. **Ward flags** — `hosp_ward_ICU/ER/IP` → `ward__icu` / `ward__er` / `ward__ip`.
7. **Merge** — left-join demographics, labs, prior-abx, prior-org, ward onto the core cohort on `anon_id`.
8. **Sparsity reduction + training** — collapse rare categories (top-40 organisms, top-25 culture sites → `other`; binary columns capped at 120 by frequency), build the pipeline, split, train, tune, evaluate, save.

**Patient-grouped split (leakage prevention):** the data is split with `GroupShuffleSplit` **grouped by `anon_id`** so the same patient never straddles splits — row-level splitting would leak patient signal and inflate metrics. Sizes: **test 20 %**, **validation 15 % of the remaining 80 %** (≈12 % of total), **train ≈ 68 %**. The script asserts zero patient overlap across all three splits.

---

## V2 Feature Schema

**46 model columns** across three groups:

| Group | Count | Columns |
|---|---:|---|
| Categorical | 4 | `culture_description`, `organism`, `antibiotic`, `gender` |
| Numeric | 5 | `age`, `wbc_median`, `cr_median`, `lactate_median`, `procalcitonin_median` |
| Binary | 37 | 18 × `prior_abxclass__*`, 16 × `prior_org__*`, 3 × `ward__*` |

The defining choice: **`antibiotic` is a feature**, not a separate model per drug. One RandomForest scores any antibiotic for any organism and can learn organism × antibiotic interactions.

**Preprocessing (`ColumnTransformer`):**
- Categorical → `SimpleImputer(most_frequent)` → `OneHotEncoder(handle_unknown='ignore', sparse_output=False)`. One-hot (not ordinal) is deliberate — it lets the forest split on a *specific* organism/antibiotic/culture value rather than collapsing them to arbitrary integers (and to a global per-antibiotic prior).
- Numeric + binary → `SimpleImputer(median)`.

**Inference note:** `prior_abxclass__*` and `prior_org__*` are **0 at inference** because the UI does not capture patient history. This reduces accuracy for complex-history patients but does not affect the core organism/antibiotic/lab signal.

---

## V2 Model Design

A single scikit-learn `RandomForestClassifier` wrapped in a `Pipeline` with the preprocessor above.

| Hyperparameter | Value | Rationale |
|---|---|---|
| `n_estimators` | **150** | Sized to fit the Render free tier (512 MB RAM) and stay under GitHub's 100 MB file limit after `compress=3`. |
| `max_depth` | **16** | Same RAM/size budget. |
| `min_samples_leaf` | **4** | Regularization against overfitting on rare organism×drug combos. |
| `max_features` | `'sqrt'` | Standard RF decorrelation. |
| `class_weight` | `'balanced_subsample'` | Target is imbalanced toward *susceptible*. |
| `random_state` | `42` | Reproducibility. |

**32 antibiotics scored:** amikacin, ampicillin, aztreonam, cefazolin, cefepime, cefotaxime, cefoxitin, cefpodoxime, ceftazidime, ceftriaxone, cefuroxime, chloramphenicol, ciprofloxacin, clarithromycin, clindamycin, doripenem, doxycycline, ertapenem, erythromycin, fosfomycin, gentamicin, levofloxacin, linezolid, meropenem, metronidazole, moxifloxacin, nitrofurantoin, streptomycin, tetracycline, tigecycline, tobramycin, vancomycin.

---

## V2 Threshold Tuning

The operating threshold is tuned on the **validation** split by sweeping 0.20–0.80. Three policies are configurable in `train_armd.py`:

- `balanced` — max balanced accuracy (tie-break F1). **Used for the shipped artifact.**
- `recall_first` — max recall subject to precision ≥ 0.85.
- `f1` — best F1.

With the `balanced` policy the selected threshold is **0.50**. Note the threshold is used for binary metrics and an optional candidate cut-off; **the API ranks by absolute probability and always returns the top 3** regardless of threshold.

---

## V2 Evaluation

Held-out **test** split (20 %, patient-grouped, never seen in training or tuning), reported for the *susceptible = 1* class at threshold 0.50 — from `split_test_summary.joblib`:

| Metric | Value |
|---|---:|
| ROC AUC | **0.851** |
| Accuracy | **0.788** |
| Balanced accuracy | **0.774** |
| Precision (S) | **0.942** |
| Recall (S) | **0.794** |
| F1 (S) | **0.862** |

**Interpretation:** high precision + moderate recall means when AURA says *susceptible*, it is usually right, at the cost of occasionally missing a susceptible drug. Combined with the antibiogram filter, the shortlist is biased toward drugs that will actually work.

**Top-3 quality:** `train_armd.py` also computes a **Top-3 hit rate** (does ≥1 truly-susceptible drug appear in the top 3?) and **Mean Reciprocal Rank** over sampled positive test contexts. These are printed during training but **not persisted** in the artifacts — re-run training to reproduce them on your split.

### Most important features

Importance is dominated by antibiotic identity, then organism, then labs/demographics (from `feature_importances.joblib`; top 10 served live at `GET /api/v2/model-info`):

| Rank | Feature | Importance |
|---:|---|---:|
| 1 | `antibiotic = ampicillin` | 0.195 |
| 2 | `antibiotic = tetracycline` | 0.090 |
| 3 | `antibiotic = meropenem` | 0.071 |
| 4 | `antibiotic = ertapenem` | 0.070 |
| 5 | `antibiotic = amikacin` | 0.060 |
| 6 | `organism = escherichia coli` | 0.026 |
| 7 | `antibiotic = nitrofurantoin` | 0.026 |
| 8 | `organism = klebsiella pneumoniae` | 0.022 |
| 9 | `cr_median` (creatinine) | 0.017 |
| 10 | `age` | 0.012 |

---

## The Antibiogram Filter

Built by `armd_model/build_antibiogram.py` → `organism_antibiotic_panel.json`.

An antibiotic is "allowed" for an organism only if the (organism, antibiotic) pair was tested **≥ 30 times** in the cohort — the **CLSI M39** minimum for antibiogram reporting. This is the clinical candidate filter applied at inference: drugs a lab never tests for an organism (e.g. *metronidazole* vs *E. coli*, *ertapenem* vs *Pseudomonas*) are excluded so they can never dominate the ranking.

- Panel covers **85 organisms**; panel size per organism: **min 1, median 7, max 22** drugs.
- Unknown organisms fall back to the full 32-drug panel rather than returning nothing.

---

## V2 Inference — the 3-layer engine

`backend/app/services/armd_predictor.py → predict()`:

```
Layer 1 — Probability scoring
  For each candidate antibiotic, build a feature row from the patient context
  with antibiotic set to that drug (prior-history features default to 0),
  run the RF pipeline → P(susceptible = 1).

Layer 2 — Antibiogram clinical filter
  Restrict candidates to the organism's allowed panel (≥30 isolates, CLSI M39).
  Unknown organism → fall back to all 32 antibiotics.

Layer 3 — Ranking
  Sort allowed candidates by absolute P(susceptible) descending.
  Top 3 → recommendations; full sorted list → all_predictions (drives the chart).
```

Each top-3 antibiotic is then enriched with dosage info (below). The ML model proposes, the antibiogram disposes, the ranking presents.

---

## Dosage Model

Implemented in `armd_model/train_dosage.py` and `backend/app/services/dosage_service.py`.

**Keying:** the dose table is keyed by `(generic, disease, age_group)`. Age is bucketed: `child` (<12), `adult` (12–64), `elderly` (≥65). Because the recommender works in culture **sites** but `d_dose` is keyed by **disease**, a site→disease map bridges them:

| Culture site | Mapped disease |
|---|---|
| `urine` | Urinary Tract Infection |
| `blood` | Bacteremia |
| `respiratory` | Pneumonia |

**Hybrid resolution (priority order):**

```
Tier 1 — Exact lookup
  dose_route_lookup.csv (840 rows: most-frequent dose/route per key, built from d_dose.csv).
  Used only when it carries a real (non-'unknown') value.

Tier 2 — RF fallback (for unseen keys, or when the lookup value is 'unknown')
  dose_model_hybrid.pkl   → dose range   (RandomForest, 500 trees, OneHotEncoder)
  route_model_hybrid.pkl  → route        (RandomForest, 500 trees)
  Features: generic, disease, age_group.

Tier 3 — Static fallback
  Built-in clinical dosing table covering all 32 antibiotics,
  so the API NEVER surfaces 'unknown'.
```

Dose and route are resolved **independently**. The `dose_source` field in the API response reports the tier used (`lookup` / `model` / `fallback`). Routes are `IV`, `PO`, or `IM`.

**Artifacts produced:** `dose_route_lookup.csv`, `dose_model_hybrid.pkl`, `route_model_hybrid.pkl`. (The script can optionally batch-evaluate against `datasets/manual_test_cases_unambiguous.csv` if present.)

---

## V2 Limitations

1. **Prior history defaults to zero** at inference (`prior_abxclass__*`, `prior_org__*` not captured in the UI).
2. **Uncalibrated probabilities** — RF `predict_proba` is rankable but not calibrated; treat as relative scores.
3. **No per-prediction explainability** — only global feature importance is exposed (TreeSHAP per request is planned).
4. **Coarse dosage keying** — depends on `(drug, mapped-disease, age band)`; not weight, renal function, or full indication.
5. **Single-institution, static snapshot** — local, time-bound resistance patterns; no external validation; periodic retraining required.
6. **32-antibiotic scope** — drugs outside the selected set cannot be scored.

---
---

# V1 legacy — CatBoost (on `main`)

> V1 is the original product line. It is **deployed and maintained from the `main` branch** and is **commented out (not deleted)** on this branch — the backend here mounts only `/api/v2/*`. The summary below is for reference; to work on V1, switch to `main`.

- **Source dataset:** Dryad microbiology cultures (`microbiology_cultures_demographics.csv` + `microbiology_cultures_microbial_resistance.csv`), joined during preprocessing. ~**22,946** cleaned samples covering **26 antibiotics** across 13 named organisms + "Other".
- **Strategy:** one `CatBoostClassifier` **per antibiotic** — `P(susceptible | organism, age, gender, kidney_function, severity)`. Independent quality filtering and SHAP per antibiotic.
- **CatBoost config:** 300 iterations, lr 0.1, depth 6, `Logloss`, computed class weights, native categorical handling.
- **Features (5):** `organism` (14 classes), `age` (bucket midpoint), `gender`, `kidney_function` *(synthetic)*, `severity` *(synthetic)*.
- **Deployment filter:** antibiotics with validation AUC < 0.65 (or degenerate class distribution) are excluded — **23 included, 3 excluded** (Cefpodoxime, Colistin AUC 0.50; Ethambutol degenerate).
- **Ranking:** raw `predict_proba` − training positive rate (baseline correction) + organism-compatibility weighting.
- **Dosing:** explicit `DosingRuleEngine` (≈20 antibiotics, 4-tier renal adjustment, severity-based duration).
- **Explainability:** CatBoost native SHAP per prediction (`/api/v1/explain`).

### V1 validation performance (included antibiotics, AUC ≥ 0.65)

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

**Average AUC (included): ~0.76.** High-AUC/low-F1 rows (e.g. Rifampin) reflect class imbalance — AUC measures rank discrimination regardless of threshold.

**V1 limitations:** synthetic `kidney_function`/`severity`; time/geography-bound corpus; no infection-site modelling; uncalibrated probabilities; conservative handling of intermediate labels.
