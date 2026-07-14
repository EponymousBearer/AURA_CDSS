# -*- coding: utf-8 -*-
"""
compare_models.py  (M2 / T2.1 + T2.3)
=====================================
Answers "why RandomForest?" with evidence: RF vs LightGBM vs CatBoost on the
IDENTICAL frozen seed-42 patient-grouped split and the IDENTICAL feature
pipeline (same one-hot preprocessor), each isotonic-calibrated the same way,
scored with the SAME M1 metric functions.

    python armd_model/compare_models.py

Reports, per model: pooled ROC-AUC, within-(organism x drug) median AUC (the
honest patient-specific-lift metric from M1), Brier before/after calibration,
Top-1/Top-3 susceptibility hit-rate, serialized artifact size, and per-request
inference latency. Writes reports/model_comparison.json + reports/model_comparison.md.

Notes:
- Training uses a fixed seed-42 subsample of the frozen TRAIN partition (see
  TRAIN_SUBSAMPLE) so all three models are compared on identical data within a
  bounded time/RAM budget; VALIDATION (calibration) and TEST (all metrics) use the
  full frozen partitions. The RF row therefore approximates — not exactly equals —
  the shipped 0.851 (which trained on the full train set).
- Hyperparameters are fair-effort, comparable-capacity defaults, not exhaustively
  tuned; the goal is a like-for-like architecture comparison, not a leaderboard.
"""

import json
import tempfile
import time
from pathlib import Path

import numpy as np
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss

import eval_common as ec
import evaluate as ev  # reuse per_cell / top_k_hit_rate / MIN_CELL_SUPPORT

RANDOM_STATE = 42
TRAIN_SUBSAMPLE = 300_000   # cap on training rows (all models see the same sample)
LATENCY_BATCH = 22          # candidate antibiotics scored per real request
LATENCY_REPEATS = 50


def build_preprocessor(categorical_cols, numeric_cols, binary_cols):
    """Identical to production (train_armd.py): one-hot categoricals, median-impute
    the numeric + binary columns. Dense output so every model sees the same matrix."""
    return ColumnTransformer(
        transformers=[
            ('cat', Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ]), categorical_cols),
            ('num', Pipeline([('imputer', SimpleImputer(strategy='median'))]),
             numeric_cols + binary_cols),
        ],
        remainder='drop',
    )


def make_models():
    """RF (production config) + fair-effort GBDT baselines of comparable capacity."""
    models = {}
    models['RandomForest'] = RandomForestClassifier(
        n_estimators=150, max_depth=16, min_samples_leaf=4, max_features='sqrt',
        class_weight='balanced_subsample', n_jobs=-1, random_state=RANDOM_STATE,
    )
    try:
        from lightgbm import LGBMClassifier
        models['LightGBM'] = LGBMClassifier(
            n_estimators=300, num_leaves=64, max_depth=16, learning_rate=0.05,
            class_weight='balanced', n_jobs=-1, random_state=RANDOM_STATE, verbose=-1,
        )
    except Exception as exc:
        print(f"  [skip] LightGBM unavailable: {exc}")
    try:
        from catboost import CatBoostClassifier
        models['CatBoost'] = CatBoostClassifier(
            iterations=300, depth=8, learning_rate=0.05, auto_class_weights='Balanced',
            random_seed=RANDOM_STATE, thread_count=-1, verbose=0, allow_writing_files=False,
        )
    except Exception as exc:
        print(f"  [skip] CatBoost unavailable: {exc}")
    return models


def artifact_size_mb(estimator) -> float:
    with tempfile.NamedTemporaryFile(suffix='.joblib', delete=False) as tf:
        path = Path(tf.name)
    try:
        joblib.dump(estimator, path, compress=3)
        return round(path.stat().st_size / 1e6, 2)
    finally:
        path.unlink(missing_ok=True)


def latency_ms(estimator, X_batch) -> float:
    estimator.predict_proba(X_batch)  # warm up
    best = np.inf
    for _ in range(LATENCY_REPEATS):
        t = time.perf_counter()
        estimator.predict_proba(X_batch)
        best = min(best, time.perf_counter() - t)
    return round(best * 1000, 2)


def main():
    ec.ensure_dirs()
    print("=" * 64)
    print("M2 — RF vs LightGBM vs CatBoost (same split, same features)")
    print("=" * 64)

    data = ec.reconstruct_splits()
    X_tr, y_tr = data['X_train'], data['y_train']
    X_va, y_va = data['X_val'], data['y_val']
    X_te, y_te = data['X_test'], data['y_test']
    feature_cols = data['feature_cols']
    cat, num, binr = data['categorical_cols'], data['numeric_cols'], data['binary_cols']

    # Fixed seed-42 subsample of the frozen TRAIN partition (identical for all models).
    if len(X_tr) > TRAIN_SUBSAMPLE:
        rng = np.random.RandomState(RANDOM_STATE)
        idx = rng.choice(len(X_tr), TRAIN_SUBSAMPLE, replace=False)
        X_tr, y_tr = X_tr.iloc[idx], y_tr.iloc[idx]
    print(f"\n  train={len(X_tr):,} (subsample)  val={len(X_va):,}  test={len(X_te):,}")

    pre = build_preprocessor(cat, num, binr).fit(X_tr)
    Xtr_t = pre.transform(X_tr)
    Xva_t = pre.transform(X_va)
    Xte_t = pre.transform(X_te)
    Xbatch = Xte_t[:LATENCY_BATCH]
    context_cols = [c for c in feature_cols if c != 'antibiotic']

    results = []
    for name, clf in make_models().items():
        print(f"\n[{name}] training...")
        t0 = time.time()
        clf.fit(Xtr_t, y_tr.to_numpy())
        train_s = round(time.time() - t0, 1)

        p_uncal = clf.predict_proba(Xte_t)[:, 1]
        cal = CalibratedClassifierCV(clf, cv='prefit', method='isotonic').fit(Xva_t, y_va.to_numpy())
        p_cal = cal.predict_proba(Xte_t)[:, 1]

        # Discrimination metrics use raw scores (calibration is monotonic → same order).
        pooled_auc = float(roc_auc_score(y_te, p_uncal))
        cells = ev.per_cell(X_te, y_te, p_uncal)
        cell_aucs = np.array([c['rf_auc'] for c in cells]) if cells else np.array([])
        median_cell_auc = float(np.median(cell_aucs)) if len(cell_aucs) else None
        topk = ev.top_k_hit_rate(X_te, y_te, p_uncal, context_cols)

        row = {
            'model': name,
            'pooled_roc_auc': round(pooled_auc, 4),
            'within_cell_median_auc': round(median_cell_auc, 4) if median_cell_auc is not None else None,
            'brier_uncalibrated': round(float(brier_score_loss(y_te, p_uncal)), 4),
            'brier_isotonic': round(float(brier_score_loss(y_te, p_cal)), 4),
            'top1_informative': round(float(topk['top1_hit_rate_informative']), 4),
            'top3_informative': round(float(topk['top3_hit_rate_informative']), 4),
            'artifact_mb_calibrated': artifact_size_mb(cal),
            'latency_ms_per_request': latency_ms(cal, Xbatch),
            'train_seconds': train_s,
        }
        results.append(row)
        print(f"  AUC={row['pooled_roc_auc']} cellAUC={row['within_cell_median_auc']} "
              f"Brier={row['brier_uncalibrated']}->{row['brier_isotonic']} "
              f"Top3={row['top3_informative']} size={row['artifact_mb_calibrated']}MB "
              f"lat={row['latency_ms_per_request']}ms train={train_s}s")

    out = {
        'meta': {
            'seed': RANDOM_STATE,
            'train_rows_used': int(len(X_tr)),
            'train_is_subsample': bool(data['manifest']['n_rows']['train'] > len(X_tr)),
            'n_test_rows': int(len(X_te)),
            'min_cell_support': ev.MIN_CELL_SUPPORT,
            'latency_batch': LATENCY_BATCH,
            'note': ('Same frozen seed-42 patient-grouped split + identical one-hot feature '
                     'pipeline for every model; isotonic-calibrated on val; scored with the M1 '
                     'metric functions. GBDT hyperparameters are comparable-capacity defaults, '
                     'not exhaustively tuned.'),
        },
        'models': results,
    }
    (ec.REPORTS_DIR / 'model_comparison.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    _write_markdown(out)
    print(f"\nWrote {ec.REPORTS_DIR / 'model_comparison.json'} + .md")


def _write_markdown(out):
    cols = [
        ('model', 'Model'), ('pooled_roc_auc', 'Pooled AUC'),
        ('within_cell_median_auc', 'Within-cell AUC'),
        ('brier_isotonic', 'Brier (cal)'), ('top3_informative', 'Top-3'),
        ('artifact_mb_calibrated', 'Size (MB)'), ('latency_ms_per_request', 'Latency (ms)'),
        ('train_seconds', 'Train (s)'),
    ]
    lines = ['# Model comparison (M2) — RF vs LightGBM vs CatBoost', '',
             f"Same frozen seed-42 split + features; isotonic-calibrated; "
             f"train subsample={out['meta']['train_rows_used']:,}, test={out['meta']['n_test_rows']:,}.", '',
             '| ' + ' | '.join(h for _, h in cols) + ' |',
             '|' + '|'.join('---' for _ in cols) + '|']
    for r in out['models']:
        lines.append('| ' + ' | '.join(str(r[k]) for k, _ in cols) + ' |')
    lines += ['', '> Within-cell AUC (0.5 = no lift over the antibiogram) is the honest '
              'patient-specific metric from M1. Discrimination metrics use raw scores; '
              'calibration is monotonic so it does not change ranking.']
    (ec.REPORTS_DIR / 'model_comparison.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
