# -*- coding: utf-8 -*-
"""
Dosage Model - Hybrid Trainer
Local training script (no Colab / Google Drive dependencies).

Reads data from: <project_root>/datasets/d_dose.csv
Writes artifacts to: <project_root>/armd_model/artifacts/

Usage:
    python armd_model/train_dosage.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# =========================
# PATHS
# =========================
DATA_PATH = Path(__file__).parent.parent / 'datasets' / 'd_dose.csv'
TEST_CASES_PATH = Path(__file__).parent.parent / 'datasets' / 'manual_test_cases_unambiguous.csv'

ARTIFACT_DIR = Path(__file__).parent / 'artifacts'
DOSE_MODEL_PATH = ARTIFACT_DIR / 'dose_model_hybrid.pkl'
ROUTE_MODEL_PATH = ARTIFACT_DIR / 'route_model_hybrid.pkl'
LOOKUP_TABLE_PATH = ARTIFACT_DIR / 'dose_route_lookup.csv'

# =========================
# SELECTED ANTIBIOTICS
# =========================
SELECTED_ANTIBIOTICS = [
    'amikacin', 'ampicillin', 'aztreonam', 'cefazolin', 'cefepime',
    'cefotaxime', 'cefoxitin', 'cefpodoxime', 'ceftazidime', 'ceftriaxone',
    'cefuroxime', 'chloramphenicol', 'ciprofloxacin', 'clarithromycin',
    'clindamycin', 'doripenem', 'doxycycline', 'ertapenem', 'erythromycin',
    'fosfomycin', 'gentamicin', 'levofloxacin', 'linezolid', 'meropenem',
    'metronidazole', 'moxifloxacin', 'nitrofurantoin', 'streptomycin',
    'tetracycline', 'tigecycline', 'tobramycin', 'vancomycin',
]

# =========================
# HELPERS
# =========================

def normalize_ab_name(x):
    if pd.isna(x):
        return float('nan')
    return str(x).strip().lower()


def build_dose_range(row):
    if pd.notna(row['min_dose_dw_mg']) and pd.notna(row['max_dose_dw_mg']):
        return f"{int(row['min_dose_dw_mg'])}-{int(row['max_dose_dw_mg'])} mg"
    if pd.notna(row['min_dose_dw_iu']) and pd.notna(row['max_dose_dw_iu']):
        return f"{int(row['min_dose_dw_iu'])}-{int(row['max_dose_dw_iu'])} units"
    return 'unknown'


def age_group_from_ranges(row):
    year_vals = [v for v in [row['min_age_y'], row['max_age_y']] if pd.notna(v)]
    if year_vals:
        avg_age = sum(year_vals) / len(year_vals)
        if avg_age < 12:
            return 'child'
        elif avg_age < 65:
            return 'adult'
        else:
            return 'elderly'
    if any(pd.notna(v) for v in [row['min_age_d'], row['max_age_d'], row['min_age_m'], row['max_age_m']]):
        return 'child'
    return 'adult'


def age_group(age: int) -> str:
    if age < 12:
        return 'child'
    elif age < 65:
        return 'adult'
    else:
        return 'elderly'


def validate_sample(sample):
    generic_norm = normalize_ab_name(sample['generic'])
    if generic_norm not in SELECTED_ANTIBIOTICS:
        raise ValueError(f"Antibiotic '{sample['generic']}' is not in the selected 32 antibiotics.")
    return generic_norm


def predict_dose_and_route(sample, dose_model, route_model, exact_dose_lookup, exact_route_lookup):
    generic_norm = validate_sample(sample)
    ag = age_group(sample['age'])
    key = (generic_norm, sample['disease'], ag)

    input_df = pd.DataFrame([{
        'generic': generic_norm,
        'disease': sample['disease'],
        'age_group': ag,
    }])

    if key in exact_dose_lookup:
        pred_dose = exact_dose_lookup[key]
        dose_source = 'lookup'
    else:
        pred_dose = dose_model.predict(input_df)[0]
        dose_source = 'model'

    if key in exact_route_lookup:
        pred_route = exact_route_lookup[key]
        route_source = 'lookup'
    else:
        pred_route = route_model.predict(input_df)[0]
        route_source = 'model'

    return {
        'generic': sample['generic'],
        'disease': sample['disease'],
        'age': sample['age'],
        'age_group': ag,
        'predicted_dose': pred_dose,
        'predicted_route': pred_route,
        'dose_source': dose_source,
        'route_source': route_source,
    }


# =========================
# MAIN
# =========================

def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Dosage Model - Hybrid Trainer")
    print("=" * 60)
    print(f"Data path    : {DATA_PATH}")
    print(f"Artifacts dir: {ARTIFACT_DIR}")

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dosage dataset not found at: {DATA_PATH}")

    # Load raw dataset
    df_raw = pd.read_csv(DATA_PATH)
    print(f"Raw shape: {df_raw.shape}")
    print(df_raw.head().to_string())

    # Normalize and filter to selected antibiotics
    df_raw['generic_original'] = df_raw['generic']
    df_raw['generic'] = df_raw['generic'].apply(normalize_ab_name)
    df_raw = df_raw[df_raw['generic'].isin(SELECTED_ANTIBIOTICS)].copy()

    print(f"Filtered raw shape (selected antibiotics only): {df_raw.shape}")
    print(f"Unique selected antibiotics found in dosage dataset: {df_raw['generic'].nunique()}")
    print("Antibiotics present:", sorted(df_raw['generic'].dropna().unique().tolist()))

    missing_in_dosage = sorted(set(SELECTED_ANTIBIOTICS) - set(df_raw['generic'].dropna().unique()))
    print("Missing from dosage dataset:", missing_in_dosage)

    # Keep only needed columns
    keep_cols = [
        'generic', 'disease',
        'min_age_d', 'max_age_d',
        'min_age_m', 'max_age_m',
        'min_age_y', 'max_age_y',
        'min_dose_dw_mg', 'max_dose_dw_mg',
        'min_dose_dw_iu', 'max_dose_dw_iu',
        'route',
    ]

    df = df_raw[[c for c in keep_cols if c in df_raw.columns]].copy()
    df = df.dropna(subset=['generic', 'disease', 'route']).copy()
    df['generic'] = df['generic'].apply(normalize_ab_name)
    df['disease'] = df['disease'].astype(str).str.strip()

    print(f"Working rows after keep/dropna: {df.shape}")
    print("Working antibiotics:", sorted(df['generic'].unique().tolist()))

    # Align route labels: keep PO, IV, IM as-is
    route_map = {'PO': 'PO', 'IV': 'IV', 'IM': 'IM'}
    df['route'] = df['route'].astype(str).str.strip().map(route_map).fillna(df['route'].astype(str).str.strip())

    # Derived features
    df['dose_range'] = df.apply(build_dose_range, axis=1)
    df['age_group'] = df.apply(age_group_from_ranges, axis=1)

    print("\nSample of derived features:")
    print(df[['generic', 'disease', 'age_group', 'dose_range', 'route']].head().to_string())

    # Inspect ambiguity
    input_cols = ['generic', 'disease', 'age_group']
    route_counts = df.groupby(input_cols + ['route']).size().reset_index(name='count')
    dose_counts = df.groupby(input_cols + ['dose_range']).size().reset_index(name='count')
    route_ambiguity = route_counts.groupby(input_cols)['route'].nunique().reset_index(name='num_routes')
    dose_ambiguity = dose_counts.groupby(input_cols)['dose_range'].nunique().reset_index(name='num_dose_ranges')

    print(f"\nUnique input combinations: {len(route_ambiguity)}")
    print(f"Inputs with multiple possible routes: {(route_ambiguity['num_routes'] > 1).sum()}")
    print(f"Inputs with multiple possible dose ranges: {(dose_ambiguity['num_dose_ranges'] > 1).sum()}")

    # Collapse to most-frequent dose and route per (generic, disease, age_group)
    lookup_df = (
        df.groupby(input_cols)
        .agg(
            dose_range=('dose_range', lambda s: s.value_counts().idxmax()),
            route=('route', lambda s: s.value_counts().idxmax()),
            support=('route', 'size'),
        )
        .reset_index()
    )

    lookup_df.to_csv(LOOKUP_TABLE_PATH, index=False)
    print(f"\nLookup table rows: {len(lookup_df)}")
    print(lookup_df.head().to_string())

    # Train fallback ML models
    feature_cols = ['generic', 'disease', 'age_group']
    X = lookup_df[feature_cols].copy()
    y_dose = lookup_df['dose_range'].copy()
    y_route = lookup_df['route'].copy()

    preprocessor = ColumnTransformer(
        transformers=[('cat', OneHotEncoder(handle_unknown='ignore'), feature_cols)]
    )

    dose_model = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(n_estimators=500, random_state=42, class_weight='balanced_subsample')),
    ])

    route_model = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(n_estimators=500, random_state=42, class_weight='balanced_subsample')),
    ])

    print(f"\nTraining rows: {len(X)}")
    print(f"Unique antibiotics in lookup_df: {lookup_df['generic'].nunique()}")
    print("Antibiotics in training set:", sorted(lookup_df['generic'].unique().tolist()))

    if len(X) == 0:
        raise ValueError("No training rows left after filtering to selected antibiotics.")
    if lookup_df['generic'].nunique() == 0:
        raise ValueError("No selected antibiotics found in lookup table.")

    print("Fitting dose model...")
    dose_model.fit(X, y_dose)
    print("Fitting route model...")
    route_model.fit(X, y_route)

    joblib.dump(dose_model, DOSE_MODEL_PATH)
    joblib.dump(route_model, ROUTE_MODEL_PATH)
    print(f"Saved dose model to  : {DOSE_MODEL_PATH}")
    print(f"Saved route model to : {ROUTE_MODEL_PATH}")
    print(f"Saved lookup table to: {LOOKUP_TABLE_PATH}")

    # Build exact-lookup dicts
    exact_dose_lookup = {
        (row['generic'], row['disease'], row['age_group']): row['dose_range']
        for _, row in lookup_df.iterrows()
    }
    exact_route_lookup = {
        (row['generic'], row['disease'], row['age_group']): row['route']
        for _, row in lookup_df.iterrows()
    }

    # Single inference example
    print("\n===== SINGLE EXAMPLE PREDICTION =====")
    sample = {'generic': 'amikacin', 'disease': 'Bacteremia', 'age': 70}
    result = predict_dose_and_route(sample, dose_model, route_model, exact_dose_lookup, exact_route_lookup)
    print(f"Predicted Dose  : {result['predicted_dose']}")
    print(f"Predicted Route : {result['predicted_route']}")
    print(f"Dose Source     : {result['dose_source']}")
    print(f"Route Source    : {result['route_source']}")

    # Optional batch test against manual test cases
    if not TEST_CASES_PATH.exists():
        print(f"\nTest cases file not found at {TEST_CASES_PATH}; skipping batch evaluation.")
        print("Training complete.")
        return

    print(f"\n===== BATCH EVALUATION on {TEST_CASES_PATH.name} =====")
    test_df = pd.read_csv(TEST_CASES_PATH)
    test_df['generic'] = test_df['generic'].apply(normalize_ab_name)
    test_df = test_df[test_df['generic'].isin(SELECTED_ANTIBIOTICS)].copy()

    print(f"Filtered test cases shape: {test_df.shape}")
    print("Test antibiotics present:", sorted(test_df['generic'].unique().tolist()))

    results = []
    for _, row in test_df.iterrows():
        sample = {
            'generic': row['generic'],
            'disease': row['disease'],
            'age': int(row['sample_age']),
        }
        pred = predict_dose_and_route(sample, dose_model, route_model, exact_dose_lookup, exact_route_lookup)

        expected_dose = row['expected_dose_range']
        expected_route = row['expected_route']
        dose_match = pred['predicted_dose'] == expected_dose
        route_match = pred['predicted_route'] == expected_route

        results.append({
            'generic': sample['generic'],
            'disease': sample['disease'],
            'age': sample['age'],
            'age_group': pred['age_group'],
            'expected_dose': expected_dose,
            'predicted_dose': pred['predicted_dose'],
            'dose_match': dose_match,
            'expected_route': expected_route,
            'predicted_route': pred['predicted_route'],
            'route_match': route_match,
            'both_match': dose_match and route_match,
            'dose_source': pred['dose_source'],
            'route_source': pred['route_source'],
        })

    results_df = pd.DataFrame(results)

    print(f"Total Test Cases : {len(results_df)}")
    print(f"Dose Correct     : {results_df['dose_match'].sum()}")
    print(f"Route Correct    : {results_df['route_match'].sum()}")
    print(f"Both Correct     : {results_df['both_match'].sum()}")
    print(f"Dose Accuracy    : {results_df['dose_match'].mean() * 100:.2f}%")
    print(f"Route Accuracy   : {results_df['route_match'].mean() * 100:.2f}%")
    print(f"Overall Accuracy : {results_df['both_match'].mean() * 100:.2f}%")

    print("\nFirst rows of results:")
    print(results_df.head().to_string())

    wrong_df = results_df[results_df['both_match'] == False].copy()
    print(f"\nWrong rows: {len(wrong_df)}")
    if len(wrong_df) > 0:
        print(wrong_df.to_string())

    print("\nTraining complete.")


if __name__ == '__main__':
    main()
