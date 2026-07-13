# -*- coding: utf-8 -*-
"""
eval_common.py  (M1)
====================
Shared plumbing for the rigorous-evaluation milestone. Reconstructs the EXACT
training table via train_armd.build_dataset(), recovers the frozen held-out
split from armd_model/splits/test_ids.json (by anon_id membership, so it is
robust to row ordering), and loads the trained pipeline.

Every M1 metric (evaluate.py, baselines.py) sources its data here so all numbers
are computed on the identical partition M0 froze (seed 42).
"""

import sys
import json
from pathlib import Path

import numpy as np
import joblib
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # so `import train_armd` works when run as a script

ARTIFACT_DIR = HERE / 'artifacts'
SPLITS_DIR = HERE / 'splits'
REPORTS_DIR = HERE.parent / 'reports'
FIG_DIR = REPORTS_DIR / 'figures'

MODEL_FILE = ARTIFACT_DIR / 'rf_top3_recommender_optimized.joblib'
SPLIT_FILE = SPLITS_DIR / 'test_ids.json'


def load_split_manifest() -> dict:
    if not SPLIT_FILE.exists():
        raise FileNotFoundError(
            f"{SPLIT_FILE} not found. Run `python armd_model/train_armd.py` first (M0/T0.3)."
        )
    with open(SPLIT_FILE) as f:
        return json.load(f)


def load_model():
    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"{MODEL_FILE} not found. Run training first (M0).")
    return joblib.load(MODEL_FILE)


def reconstruct_splits(verbose: bool = True):
    """Rebuild the modelling table and slice it into the frozen train/val/test
    partitions by anon_id. Returns a dict of DataFrames/Series + metadata.

    Verifies the recovered test-row count matches the persisted manifest so a
    silent data drift can never masquerade as a valid evaluation.
    """
    import train_armd  # local import; module-level code is cheap, main() is __main__-gated

    manifest = load_split_manifest()
    data = train_armd.build_dataset()
    df = data['df']
    X = data['X']
    y = data['y']

    anon = df['anon_id'].astype(str)
    train_ids = set(manifest['train_anon_ids'])
    val_ids = set(manifest['val_anon_ids'])
    test_ids = set(manifest['test_anon_ids'])

    m_train = anon.isin(train_ids).values
    m_val = anon.isin(val_ids).values
    m_test = anon.isin(test_ids).values

    out = {
        'df': df,
        'X_train': X[m_train], 'y_train': y[m_train],
        'X_val': X[m_val], 'y_val': y[m_val],
        'X_test': X[m_test], 'y_test': y[m_test],
        'feature_cols': data['feature_cols'],
        'categorical_cols': data['categorical_cols'],
        'numeric_cols': data['numeric_cols'],
        'binary_cols': data['binary_cols'],
        'manifest': manifest,
    }

    # Integrity guard: recovered split must match what M0 froze.
    exp = manifest['n_rows']
    got = {'train': int(m_train.sum()), 'val': int(m_val.sum()), 'test': int(m_test.sum())}
    if verbose:
        print(f"\n[eval_common] recovered rows {got} vs manifest {exp}")
    assert got == exp, (
        f"Split reconstruction mismatch: got {got}, manifest {exp}. "
        "The dataset build is not reproducing the frozen split — investigate before trusting metrics."
    )
    return out


def safe_auc(y_true, y_score):
    """ROC-AUC that returns NaN when a stratum has a single class (undefined)."""
    y_true = np.asarray(y_true)
    if len(np.unique(y_true)) < 2:
        return float('nan')
    try:
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        return float('nan')


def ensure_dirs():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
