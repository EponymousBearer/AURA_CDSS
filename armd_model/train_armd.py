# -*- coding: utf-8 -*-
"""
ARMD RandomForest Top-3 Antibiotic Recommender
Local training script (no Colab / Google Drive dependencies).

Reads CSV data from: <project_root>/datasets/
Writes model artifacts to: <project_root>/armd_model/artifacts/

Usage:
    python armd_model/train_armd.py
"""

import gc
import json
import re
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 200)
pd.set_option("display.max_rows", 100)

# =========================
# PATHS
# =========================
BASE_DIR = Path(__file__).parent.parent / 'datasets'
ARTIFACT_DIR = Path(__file__).parent / 'artifacts'

# =========================
# CONFIG
# =========================
CHUNK_SIZE = 150_000
MAX_PRIOR_ORGS = 50
N_ESTIMATORS = 300
MAX_DEPTH = 18
MIN_SAMPLES_LEAF = 3
TEST_SIZE = 0.20
VALID_SIZE_FROM_TRAIN = 0.15
RANDOM_STATE = 42

TOP_N_ORGANISMS = 40
TOP_N_CULTURE_SITES = 25
MAX_BINARY_FEATURES = 120

THRESHOLD_POLICY = 'recall_first'
MIN_PRECISION_FOR_RECALL_POLICY = 0.85

SELECTED_ANTIBIOTICS = [
    'amikacin', 'ampicillin', 'aztreonam', 'cefazolin', 'cefepime', 'cefotaxime',
    'cefoxitin', 'cefpodoxime', 'ceftazidime', 'ceftriaxone', 'cefuroxime',
    'chloramphenicol', 'ciprofloxacin', 'clarithromycin', 'clindamycin', 'doripenem',
    'doxycycline', 'ertapenem', 'erythromycin', 'fosfomycin', 'gentamicin',
    'levofloxacin', 'linezolid', 'meropenem', 'metronidazole', 'moxifloxacin',
    'nitrofurantoin', 'streptomycin', 'tetracycline', 'tigecycline', 'tobramycin',
    'vancomycin',
]

REQUIRED_FILES = [
    'microbiology_cultures_cohort.csv',
    'microbiology_cultures_demographics.csv',
    'microbiology_cultures_labs.csv',
    'microbiology_cultures_antibiotic_class_exposure.csv',
    'microbiology_culture_prior_infecting_organism.csv',
    'microbiology_cultures_ward_info.csv',
]

# =========================
# HELPERS
# =========================

def find_file(base_dir: Path, filename: str):
    for path in base_dir.rglob(filename):
        return path
    return None


def read_header(path: Path):
    return pd.read_csv(path, nrows=0).columns.tolist()


def normalize_antibiotic_name(x):
    if pd.isna(x):
        return float('nan')
    x = str(x).strip().lower()
    x = x.replace('_', ' ').replace('-', ' ')
    x = ' '.join(x.split())
    return x


def map_susceptibility(value):
    if pd.isna(value):
        return float('nan')
    s = str(value).strip().lower()
    if s in {'susceptible', 's', 'sus'}:
        return 1
    if s in {'resistant', 'r', 'res'}:
        return 0
    return float('nan')


def choose_existing_columns(path: Path, wanted_cols):
    header = set(read_header(path))
    return [c for c in wanted_cols if c in header]


def print_shape(name, df):
    print(f"  {name}: {df.shape[0]:,} rows x {df.shape[1]:,} cols")


def optimize_binary_columns(df):
    for col in df.columns:
        if (
            col.startswith('prior_abxclass__')
            or col.startswith('prior_org__')
            or col.startswith('ward__')
        ):
            df[col] = df[col].fillna(0).astype('int8')
    return df


def convert_age_to_numeric(x):
    if pd.isna(x):
        return float('nan')
    x = str(x).strip().lower()

    age_map = {
        '0-2 years': 1,
        '3-5 years': 4,
        '6-12 years': 9,
        '13-17 years': 15,
        '18-24 years': 21,
        '25-34 years': 29.5,
        '35-44 years': 39.5,
        '45-54 years': 49.5,
        '55-64 years': 59.5,
        '65-74 years': 69.5,
        '75-84 years': 79.5,
        '85+ years': 90,
        'less than 1 year': 0.5,
        'unknown': float('nan'),
    }

    if x in age_map:
        return age_map[x]

    nums = re.findall(r'\d+', x)
    if len(nums) >= 2:
        return (float(nums[0]) + float(nums[1])) / 2
    elif len(nums) == 1:
        return float(nums[0])

    return float('nan')


def evaluate_binary_classifier(y_true, y_prob, threshold=0.5, title='Evaluation'):
    y_pred = (y_prob >= threshold).astype(int)
    print(f"\n===== {title} =====")
    print(f"Threshold: {threshold:.3f}")
    print("Accuracy:", round(accuracy_score(y_true, y_pred), 4))
    print("Balanced Accuracy:", round(balanced_accuracy_score(y_true, y_pred), 4))
    print("Precision (Susceptible=1):", round(precision_score(y_true, y_pred, zero_division=0), 4))
    print("Recall (Susceptible=1):", round(recall_score(y_true, y_pred, zero_division=0), 4))
    print("F1 (Susceptible=1):", round(f1_score(y_true, y_pred, zero_division=0), 4))
    try:
        print("ROC-AUC:", round(roc_auc_score(y_true, y_prob), 4))
        print("Average Precision:", round(average_precision_score(y_true, y_prob), 4))
    except Exception as e:
        print("AUC metrics unavailable:", e)
    print("\nConfusion Matrix [[TN, FP], [FN, TP]]:")
    print(confusion_matrix(y_true, y_pred))
    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, digits=4))
    return y_pred


def recommend_top3(patient_input, model, feature_cols, candidate_antibiotics, threshold=None):
    """
    Scores each candidate antibiotic for one patient/culture case.
    Returns top3 and all_scores DataFrames.
    """
    rows = []
    clean_candidates = [normalize_antibiotic_name(ab) for ab in candidate_antibiotics]

    for ab in clean_candidates:
        row = {c: 0 for c in feature_cols}
        for k, v in patient_input.items():
            if k in row:
                row[k] = v

        if 'culture_description' in row and isinstance(row['culture_description'], str):
            row['culture_description'] = row['culture_description'].strip().lower()
        if 'organism' in row and isinstance(row['organism'], str):
            row['organism'] = row['organism'].strip().lower()
        if 'gender' in row and isinstance(row['gender'], str):
            row['gender'] = row['gender'].strip().lower()

        row['antibiotic'] = ab
        rows.append(row)

    score_df = pd.DataFrame(rows)[feature_cols]
    probs = model.predict_proba(score_df)[:, 1]

    result = pd.DataFrame({
        'antibiotic': clean_candidates,
        'susceptible_probability': probs,
    }).sort_values('susceptible_probability', ascending=False).reset_index(drop=True)

    if threshold is not None:
        result = result[result['susceptible_probability'] >= threshold].reset_index(drop=True)

    return result.head(3), result


# =========================
# MAIN PIPELINE
# =========================

def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ARMD RandomForest Top-3 Recommender - Training Pipeline")
    print("=" * 60)
    print(f"Datasets dir : {BASE_DIR}")
    print(f"Artifacts dir: {ARTIFACT_DIR}")

    # Resolve file paths
    paths = {fname: find_file(BASE_DIR, fname) for fname in REQUIRED_FILES}

    for fname, path in paths.items():
        status = str(path) if path else "NOT FOUND"
        print(f"  {fname}: {status}")

    missing_required = [
        fname for fname in REQUIRED_FILES[:-1]
        if paths[fname] is None
    ]
    if missing_required:
        raise FileNotFoundError(f"Missing required file(s): {missing_required}")

    USE_WARD = paths['microbiology_cultures_ward_info.csv'] is not None
    print(f"USE_WARD = {USE_WARD}")

    # [1/8] LOAD & FILTER CORE COHORT
    print("\n[1/8] Loading core cohort...")
    core_path = paths['microbiology_cultures_cohort.csv']
    core_cols = choose_existing_columns(core_path, [
        'anon_id', 'order_proc_id_coded', 'culture_description',
        'was_positive', 'organism', 'antibiotic', 'susceptibility',
    ])

    core = pd.read_csv(core_path, usecols=core_cols, dtype='string', low_memory=False)

    if 'was_positive' in core.columns:
        core['was_positive_norm'] = core['was_positive'].astype('string').str.strip().str.lower()
        positive_values = {'1', 'true', 't', 'yes', 'y', 'positive'}
        core = core[core['was_positive_norm'].isin(positive_values)].copy()

    core['antibiotic'] = core['antibiotic'].map(normalize_antibiotic_name)
    core = core[core['antibiotic'].isin(SELECTED_ANTIBIOTICS)].copy()

    core['target'] = core['susceptibility'].map(map_susceptibility)
    core = core.dropna(subset=['anon_id', 'organism', 'culture_description', 'antibiotic', 'target']).copy()
    core['target'] = core['target'].astype('int8')

    keep_cols = [c for c in ['anon_id', 'culture_description', 'organism', 'antibiotic', 'target'] if c in core.columns]
    core = core[keep_cols].drop_duplicates().reset_index(drop=True)
    print_shape('core filtered', core)
    print(core.to_string(max_rows=5))

    cohort_ids = set(core['anon_id'].astype(str).unique())
    print(f"  Unique anon_id count: {len(cohort_ids):,}")

    # [2/8] DEMOGRAPHICS
    print("\n[2/8] Loading demographics...")
    demo_path = paths['microbiology_cultures_demographics.csv']
    demo_cols = choose_existing_columns(demo_path, ['anon_id', 'age', 'gender'])

    demo = pd.read_csv(
        demo_path,
        usecols=demo_cols,
        dtype={'anon_id': 'string', 'age': 'string', 'gender': 'string'},
        low_memory=False,
    )
    demo = demo[demo['anon_id'].astype(str).isin(cohort_ids)].copy()
    demo = demo.drop_duplicates(subset=['anon_id'])
    demo['age'] = demo['age'].apply(convert_age_to_numeric).astype('float32')
    print_shape('demographics filtered', demo)

    # [3/8] LABS
    print("\n[3/8] Loading labs...")
    labs_path = paths['microbiology_cultures_labs.csv']
    labs_cols = choose_existing_columns(labs_path, [
        'anon_id', 'wbc_median', 'cr_median', 'lactate_median', 'procalcitonin_median',
    ])

    labs = pd.read_csv(
        labs_path,
        usecols=labs_cols,
        dtype={
            'anon_id': 'string',
            'wbc_median': 'float32',
            'cr_median': 'float32',
            'lactate_median': 'float32',
            'procalcitonin_median': 'float32',
        },
        low_memory=False,
    )
    labs = labs[labs['anon_id'].astype(str).isin(cohort_ids)].copy()
    labs = labs.drop_duplicates(subset=['anon_id'])
    print_shape('labs filtered', labs)

    # [4/8] PRIOR ANTIBIOTIC CLASS EXPOSURE (CHUNKED)
    print("\n[4/8] Loading prior antibiotic class exposure (chunked)...")
    abx_path = paths['microbiology_cultures_antibiotic_class_exposure.csv']
    abx_header = read_header(abx_path)

    abx_anon_col = 'anon_id' if 'anon_id' in abx_header else None
    abx_class_col = 'antibiotic_class' if 'antibiotic_class' in abx_header else None

    if abx_anon_col is None or abx_class_col is None:
        raise ValueError("Expected columns anon_id and antibiotic_class not found in antibiotic exposure file.")

    abx_sets = {}

    for chunk in pd.read_csv(
        abx_path,
        usecols=[abx_anon_col, abx_class_col],
        dtype='string',
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):
        chunk = chunk[chunk[abx_anon_col].astype(str).isin(cohort_ids)]
        chunk = chunk.dropna(subset=[abx_anon_col, abx_class_col])
        if chunk.empty:
            continue

        chunk[abx_class_col] = (
            chunk[abx_class_col].astype('string').str.strip().str.lower().str.replace(r'\s+', '_', regex=True)
        )

        grouped = chunk.groupby(abx_anon_col)[abx_class_col].agg(lambda s: set(s.tolist()))
        for anon_id, cls_set in grouped.items():
            if anon_id not in abx_sets:
                abx_sets[anon_id] = set()
            abx_sets[anon_id].update(cls_set)

        del chunk, grouped
        gc.collect()

    all_abx_classes = sorted({c for s in abx_sets.values() for c in s if pd.notna(c)})
    print(f"  Unique antibiotic classes found: {len(all_abx_classes)}")

    abx_rows = []
    for anon_id in cohort_ids:
        row = {'anon_id': anon_id}
        cls_set = abx_sets.get(anon_id, set())
        for cls in all_abx_classes:
            row[f'prior_abxclass__{cls}'] = 1 if cls in cls_set else 0
        abx_rows.append(row)

    abx_df = pd.DataFrame(abx_rows)
    for c in abx_df.columns:
        if c != 'anon_id':
            abx_df[c] = abx_df[c].astype('int8')
    print_shape('prior antibiotic class features', abx_df)

    # [5/8] PRIOR INFECTING ORGANISMS (CHUNKED, WIDTH-LIMITED)
    print("\n[5/8] Loading prior infecting organisms (chunked)...")
    prior_org_path = paths['microbiology_culture_prior_infecting_organism.csv']
    prior_header = read_header(prior_org_path)

    prior_anon_col = 'anon_id' if 'anon_id' in prior_header else None
    possible_prior_org_cols = ['prior_organism', 'prior_infecting_organism', 'organism']
    prior_org_col = next((c for c in possible_prior_org_cols if c in prior_header), None)

    if prior_anon_col is None or prior_org_col is None:
        raise ValueError(
            f"Expected anon_id and one of {possible_prior_org_cols} in prior organism file. "
            f"Header has: {prior_header[:25]}"
        )

    prior_sets = {}
    prior_freq = {}

    for chunk in pd.read_csv(
        prior_org_path,
        usecols=[prior_anon_col, prior_org_col],
        dtype='string',
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):
        chunk = chunk[chunk[prior_anon_col].astype(str).isin(cohort_ids)]
        chunk = chunk.dropna(subset=[prior_anon_col, prior_org_col])
        if chunk.empty:
            continue

        chunk[prior_org_col] = (
            chunk[prior_org_col].astype('string').str.strip().str.lower().str.replace(r'\s+', '_', regex=True)
        )

        grouped = chunk.groupby(prior_anon_col)[prior_org_col].agg(lambda s: set(s.tolist()))
        for anon_id, org_set in grouped.items():
            if anon_id not in prior_sets:
                prior_sets[anon_id] = set()
            prior_sets[anon_id].update(org_set)

        vc = chunk[prior_org_col].value_counts(dropna=True)
        for k, v in vc.items():
            prior_freq[k] = prior_freq.get(k, 0) + int(v)

        del chunk, grouped, vc
        gc.collect()

    top_prior_orgs = [
        k for k, _ in sorted(prior_freq.items(), key=lambda x: x[1], reverse=True)[:MAX_PRIOR_ORGS]
    ]
    print(f"  Top prior organisms retained: {len(top_prior_orgs)}")
    print(f"  Sample: {top_prior_orgs[:15]}")

    prior_rows = []
    for anon_id in cohort_ids:
        row = {'anon_id': anon_id}
        org_set = prior_sets.get(anon_id, set())
        for org in top_prior_orgs:
            row[f'prior_org__{org}'] = 1 if org in org_set else 0
        prior_rows.append(row)

    prior_org_df = pd.DataFrame(prior_rows)
    for c in prior_org_df.columns:
        if c != 'anon_id':
            prior_org_df[c] = prior_org_df[c].astype('int8')
    print_shape('prior organism features', prior_org_df)

    # [6/8] OPTIONAL WARD FLAGS
    print("\n[6/8] Loading ward flags...")
    if USE_WARD:
        ward_path = paths['microbiology_cultures_ward_info.csv']
        ward_wanted = ['anon_id', 'hosp_ward_ICU', 'hosp_ward_ER', 'hosp_ward_IP', 'hosp_ward_OP']
        ward_cols = choose_existing_columns(ward_path, ward_wanted)

        ward = pd.read_csv(ward_path, usecols=ward_cols, dtype='string', low_memory=False)
        ward = ward[ward['anon_id'].astype(str).isin(cohort_ids)].copy()
        ward = ward.drop_duplicates(subset=['anon_id'])

        for c in ward.columns:
            if c == 'anon_id':
                continue
            ward[c] = (
                ward[c].astype('string').str.strip().str.lower().isin(['1', 'true', 't', 'yes', 'y'])
            ).astype('int8')

        rename_map = {'hosp_ward_ICU': 'ward__icu', 'hosp_ward_ER': 'ward__er', 'hosp_ward_IP': 'ward__ip'}
        keep = ['anon_id'] + [c for c in ['hosp_ward_ICU', 'hosp_ward_ER', 'hosp_ward_IP'] if c in ward.columns]
        ward = ward[keep].rename(columns=rename_map)
        print_shape('ward filtered', ward)
        print(ward.head().to_string())
    else:
        ward = None
        print("  Ward file not found, continuing without ward features.")

    # [7/8] MERGE EVERYTHING
    print("\n[7/8] Merging all tables...")
    df = core.merge(demo, on='anon_id', how='left')
    df = df.merge(labs, on='anon_id', how='left')
    df = df.merge(abx_df, on='anon_id', how='left')
    df = df.merge(prior_org_df, on='anon_id', how='left')
    if ward is not None:
        df = df.merge(ward, on='anon_id', how='left')

    df = optimize_binary_columns(df)
    df = df.drop_duplicates().reset_index(drop=True)
    print_shape('final merged dataset', df)
    print(df.to_string(max_rows=5))
    print("Target distribution:")
    print(df['target'].value_counts(dropna=False))
    print("Selected antibiotics in final data:", sorted(df['antibiotic'].dropna().unique().tolist()))

    # [8/8] SPARSITY REDUCTION + FEATURE ENGINEERING
    print("\n[8/8] Feature engineering and model training...")

    for col in ['organism', 'culture_description', 'antibiotic', 'gender']:
        if col in df.columns:
            df[col] = df[col].astype('string').str.strip().str.lower().fillna('unknown')

    if 'organism' in df.columns:
        top_orgs = df['organism'].value_counts().head(TOP_N_ORGANISMS).index
        df['organism'] = df['organism'].where(df['organism'].isin(top_orgs), 'other')
        print(f"  Organism categories retained: {len(top_orgs)} + other")

    if 'culture_description' in df.columns:
        top_cultures = df['culture_description'].value_counts().head(TOP_N_CULTURE_SITES).index
        df['culture_description'] = df['culture_description'].where(
            df['culture_description'].isin(top_cultures), 'other'
        )
        print(f"  Culture description categories retained: {len(top_cultures)} + other")

    all_binary_cols = [
        c for c in df.columns
        if c.startswith('prior_abxclass__') or c.startswith('prior_org__') or c.startswith('ward__')
    ]

    if len(all_binary_cols) > MAX_BINARY_FEATURES:
        binary_freq = df[all_binary_cols].sum(axis=0).sort_values(ascending=False)
        keep_binary_cols = binary_freq.head(MAX_BINARY_FEATURES).index.tolist()
        drop_binary_cols = [c for c in all_binary_cols if c not in keep_binary_cols]
        df = df.drop(columns=drop_binary_cols)
        print(f"  Binary features reduced from {len(all_binary_cols)} to {len(keep_binary_cols)}")
    else:
        keep_binary_cols = all_binary_cols
        print(f"  Binary features kept: {len(keep_binary_cols)}")

    df = df.drop_duplicates().reset_index(drop=True)

    feature_cols = [c for c in df.columns if c not in ['anon_id', 'target']]
    X = df[feature_cols].copy()
    y = df['target'].astype('int8').copy()

    categorical_cols = [c for c in ['culture_description', 'organism', 'antibiotic', 'gender'] if c in X.columns]
    numeric_cols = [c for c in ['age', 'wbc_median', 'cr_median', 'lactate_median', 'procalcitonin_median'] if c in X.columns]
    binary_cols = [
        c for c in X.columns
        if c.startswith('prior_abxclass__') or c.startswith('prior_org__') or c.startswith('ward__')
    ]

    print(f"  Final X shape: {X.shape}")
    print(f"  categorical_cols: {categorical_cols}")
    print(f"  numeric_cols: {numeric_cols}")
    print(f"  binary_cols count: {len(binary_cols)}")
    print("  Target distribution (proportions):")
    print(y.value_counts(normalize=True).rename('proportion'))

    # TRAIN / VAL / TEST SPLIT
    print("\n  Splitting data...")
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full,
        test_size=VALID_SIZE_FROM_TRAIN,
        random_state=RANDOM_STATE,
        stratify=y_train_full,
    )
    print(f"  Train: {X_train.shape}  Validation: {X_val.shape}  Test: {X_test.shape}")
    print("  Train target distribution:")
    print(y_train.value_counts(normalize=True).rename('proportion'))

    # BUILD SKLEARN PIPELINE
    preprocessor = ColumnTransformer(
        transformers=[
            (
                'cat',
                Pipeline([
                    ('imputer', SimpleImputer(strategy='most_frequent')),
                    ('encoder', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)),
                ]),
                categorical_cols,
            ),
            (
                'num',
                Pipeline([('imputer', SimpleImputer(strategy='median'))]),
                numeric_cols + binary_cols,
            ),
        ],
        remainder='drop',
        sparse_threshold=0.0,
    )

    rf = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        max_features='sqrt',
        class_weight='balanced_subsample',
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )

    model = Pipeline([('prep', preprocessor), ('rf', rf)])

    print("  Training RandomForest (this may take a few minutes)...")
    model.fit(X_train, y_train)
    print("  Training complete.")

    # THRESHOLD TUNING
    val_prob = model.predict_proba(X_val)[:, 1]
    test_prob = model.predict_proba(X_test)[:, 1]

    evaluate_binary_classifier(y_val, val_prob, threshold=0.50, title='VALIDATION @ default 0.50')

    thresholds = [round(t, 2) for t in list(range(20, 81))]
    thresholds = [t / 100.0 for t in range(20, 81)]
    rows_thr = []
    for t in thresholds:
        yp = (val_prob >= t).astype(int)
        rows_thr.append({
            'threshold': t,
            'accuracy': accuracy_score(y_val, yp),
            'balanced_accuracy': balanced_accuracy_score(y_val, yp),
            'precision_1': precision_score(y_val, yp, zero_division=0),
            'recall_1': recall_score(y_val, yp, zero_division=0),
            'f1_1': f1_score(y_val, yp, zero_division=0),
            'false_negatives': int(((y_val == 1) & (yp == 0)).sum()),
            'false_positives': int(((y_val == 0) & (yp == 1)).sum()),
        })

    threshold_df = pd.DataFrame(rows_thr)

    if THRESHOLD_POLICY == 'recall_first':
        eligible = threshold_df[threshold_df['precision_1'] >= MIN_PRECISION_FOR_RECALL_POLICY]
        if len(eligible) == 0:
            print(f"  No threshold reached precision >= {MIN_PRECISION_FOR_RECALL_POLICY}; falling back to best F1.")
            best_row = threshold_df.sort_values(['f1_1', 'balanced_accuracy'], ascending=False).iloc[0]
        else:
            best_row = eligible.sort_values(['recall_1', 'f1_1', 'balanced_accuracy'], ascending=False).iloc[0]
    else:
        best_row = threshold_df.sort_values(['f1_1', 'balanced_accuracy'], ascending=False).iloc[0]

    BEST_THRESHOLD = float(best_row['threshold'])

    print("\n===== TOP THRESHOLD CANDIDATES ON VALIDATION =====")
    print(threshold_df.sort_values(['f1_1', 'balanced_accuracy'], ascending=False).head(10).to_string())
    print(f"Selected BEST_THRESHOLD = {BEST_THRESHOLD:.3f} using policy = {THRESHOLD_POLICY}")

    evaluate_binary_classifier(y_test, test_prob, threshold=0.50, title='TEST @ default 0.50')
    y_test_pred = evaluate_binary_classifier(y_test, test_prob, threshold=BEST_THRESHOLD, title='TEST @ tuned threshold')

    split_test_summary = pd.DataFrame([
        {
            'split': 'test',
            'threshold': 0.50,
            'accuracy': accuracy_score(y_test, (test_prob >= 0.50).astype(int)),
            'balanced_accuracy': balanced_accuracy_score(y_test, (test_prob >= 0.50).astype(int)),
            'precision_1': precision_score(y_test, (test_prob >= 0.50).astype(int), zero_division=0),
            'recall_1': recall_score(y_test, (test_prob >= 0.50).astype(int), zero_division=0),
            'f1_1': f1_score(y_test, (test_prob >= 0.50).astype(int), zero_division=0),
            'roc_auc': roc_auc_score(y_test, test_prob),
        },
        {
            'split': 'test',
            'threshold': BEST_THRESHOLD,
            'accuracy': accuracy_score(y_test, y_test_pred),
            'balanced_accuracy': balanced_accuracy_score(y_test, y_test_pred),
            'precision_1': precision_score(y_test, y_test_pred, zero_division=0),
            'recall_1': recall_score(y_test, y_test_pred, zero_division=0),
            'f1_1': f1_score(y_test, y_test_pred, zero_division=0),
            'roc_auc': roc_auc_score(y_test, test_prob),
        },
    ])

    print("\n===== REPORT SUMMARY =====")
    print(split_test_summary.to_string())

    # TOP-3 RECOMMENDATION EVALUATION
    TOP3_EVAL_CONTEXTS = 500
    context_cols = [c for c in feature_cols if c != 'antibiotic']
    test_eval = X_test.copy()
    test_eval['actual_target'] = y_test.values
    pos_contexts = test_eval[test_eval['actual_target'] == 1].drop_duplicates(subset=context_cols)

    if len(pos_contexts) == 0:
        print("No positive contexts available for Top-3 evaluation.")
    else:
        sample_contexts = pos_contexts.sample(
            n=min(TOP3_EVAL_CONTEXTS, len(pos_contexts)), random_state=RANDOM_STATE
        )
        hits = []
        reciprocal_ranks = []

        for _, ctx_row in sample_contexts.iterrows():
            ctx = ctx_row[context_cols].to_dict()
            mask = (test_eval[context_cols] == pd.Series(ctx)).all(axis=1)
            actual_sus_abx = set(
                test_eval.loc[mask & (test_eval['actual_target'] == 1), 'antibiotic'].astype(str).tolist()
            )
            top3, all_scores = recommend_top3(ctx, model, feature_cols, SELECTED_ANTIBIOTICS, threshold=None)
            ranked = all_scores['antibiotic'].tolist()
            top3_set = set(ranked[:3])
            hit = len(actual_sus_abx.intersection(top3_set)) > 0
            hits.append(hit)
            rr = 0.0
            for rank, ab in enumerate(ranked, start=1):
                if ab in actual_sus_abx:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

        print("\n===== TOP-3 RECOMMENDATION TESTING =====")
        print(f"Sampled contexts     : {len(sample_contexts)}")
        print(f"Top-3 Hit Rate       : {round(float(__import__('numpy').mean(hits)), 4)}")
        print(f"Mean Reciprocal Rank : {round(float(__import__('numpy').mean(reciprocal_ranks)), 4)}")

    # FEATURE IMPORTANCE
    rf_model = model.named_steps['rf']
    processed_feature_names = categorical_cols + numeric_cols + binary_cols
    importances = pd.DataFrame({
        'feature': processed_feature_names,
        'importance': rf_model.feature_importances_,
    }).sort_values('importance', ascending=False).reset_index(drop=True)

    print("\nTop 30 important features:")
    print(importances.head(30).to_string())
    print("Very low-importance features (<0.001):", int((importances['importance'] < 0.001).sum()))

    # SAVE ARTIFACTS
    print(f"\nSaving artifacts to: {ARTIFACT_DIR}")
    joblib.dump(model, ARTIFACT_DIR / 'rf_top3_recommender_optimized.joblib')
    joblib.dump(feature_cols, ARTIFACT_DIR / 'feature_cols.joblib')
    joblib.dump(SELECTED_ANTIBIOTICS, ARTIFACT_DIR / 'selected_antibiotics.joblib')
    joblib.dump(importances, ARTIFACT_DIR / 'feature_importances.joblib')
    joblib.dump(BEST_THRESHOLD, ARTIFACT_DIR / 'best_threshold.joblib')
    joblib.dump(split_test_summary, ARTIFACT_DIR / 'split_test_summary.joblib')

    meta = {
        'categorical_cols': categorical_cols,
        'numeric_cols': numeric_cols,
        'binary_cols': binary_cols,
        'selected_antibiotics': SELECTED_ANTIBIOTICS,
        'max_prior_orgs': MAX_PRIOR_ORGS,
        'top_n_organisms': TOP_N_ORGANISMS,
        'top_n_culture_sites': TOP_N_CULTURE_SITES,
        'max_binary_features': MAX_BINARY_FEATURES,
        'best_threshold': BEST_THRESHOLD,
        'threshold_policy': THRESHOLD_POLICY,
        'target_mapping': {'Resistant': 0, 'Susceptible': 1},
    }
    with open(ARTIFACT_DIR / 'metadata_optimized.json', 'w') as f:
        json.dump(meta, f, indent=2)

    print("Artifacts saved successfully.")

    # EXAMPLE INFERENCE
    print("\n===== EXAMPLE INFERENCE =====")
    sample_patient = {
        'culture_description': 'urine',
        'organism': 'klebsiella pneumoniae',
        'age': 45,
        'gender': 'female',
        'wbc_median': 12000,
        'cr_median': 1.2,
        'lactate_median': 1.8,
        'procalcitonin_median': 2.5,
        'ward__icu': 0,
        'ward__er': 1,
        'ward__ip': 1,
    }
    top3, all_scores = recommend_top3(
        patient_input=sample_patient,
        model=model,
        feature_cols=feature_cols,
        candidate_antibiotics=SELECTED_ANTIBIOTICS,
        threshold=None,
    )
    print(f"Best threshold from validation: {BEST_THRESHOLD:.3f}")
    print("Top-3 recommendations:")
    print(top3.to_string())

    unseen_patient = {
        'culture_description': 'unknown_site',
        'organism': 'unknown_organism',
        'age': 60,
        'gender': 'unknown',
        'wbc_median': 9000,
        'cr_median': 0.9,
        'lactate_median': 1.1,
        'procalcitonin_median': 0.2,
    }
    top3_unseen, _ = recommend_top3(unseen_patient, model, feature_cols, SELECTED_ANTIBIOTICS)
    print("\nUnseen category sanity check (top-3):")
    print(top3_unseen.to_string())

    print("\nPipeline complete.")


if __name__ == '__main__':
    main()
