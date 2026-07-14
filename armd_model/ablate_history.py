# -*- coding: utf-8 -*-
"""
ablate_history.py  (M3 / T3.3)
==============================
Does patient prior-history actually add lift? Measures the model's discrimination
on the frozen seed-42 held-out test split WITH the prior-history features as
recorded, versus with them ZEROED at inference (the pre-M3 behaviour) — an
ablation, holding the trained model fixed:

    python armd_model/ablate_history.py

Reports the AUC delta overall and, more informatively, on the subset of test rows
that actually carry prior history (where zeroing can matter at all). Writes
reports/history_ablation.json.
"""

import json

import numpy as np

import eval_common as ec


def main():
    ec.ensure_dirs()
    print("M3/T3.3 — prior-history ablation")

    data = ec.reconstruct_splits()
    model = ec.load_model()  # raw RF, matches M1 pooled AUC 0.851
    X_te, y_te = data['X_test'].copy(), data['y_test']
    cols = data['feature_cols']
    prior_cols = [c for c in cols if c.startswith(('prior_abxclass__', 'prior_org__'))]
    print(f"  test rows={len(X_te):,}  prior-history feature cols={len(prior_cols)}")

    # Rows that actually carry any prior history (where zeroing can change anything).
    has_hist = (X_te[prior_cols].fillna(0).to_numpy() != 0).any(axis=1)
    n_hist = int(has_hist.sum())

    # WITH history (as recorded) vs history ZEROED at inference.
    p_full = model.predict_proba(X_te[cols])[:, 1]
    X_zero = X_te.copy()
    X_zero[prior_cols] = 0
    p_zero = model.predict_proba(X_zero[cols])[:, 1]

    auc_full = ec.safe_auc(y_te, p_full)
    auc_zero = ec.safe_auc(y_te, p_zero)

    # On the history-bearing subset only (the population where the feature is live).
    yh = y_te.to_numpy()[has_hist]
    auc_full_h = ec.safe_auc(yh, p_full[has_hist])
    auc_zero_h = ec.safe_auc(yh, p_zero[has_hist])

    mean_abs_shift = float(np.mean(np.abs(p_full - p_zero)))
    mean_abs_shift_h = float(np.mean(np.abs(p_full[has_hist] - p_zero[has_hist]))) if n_hist else 0.0

    result = {
        'n_test_rows': int(len(X_te)),
        'n_prior_history_cols': len(prior_cols),
        'n_rows_with_history': n_hist,
        'frac_rows_with_history': round(n_hist / len(X_te), 4),
        'overall': {
            'auc_with_history': auc_full,
            'auc_history_zeroed': auc_zero,
            'auc_lift_from_history': round(auc_full - auc_zero, 5),
            'mean_abs_prob_shift': round(mean_abs_shift, 5),
        },
        'history_bearing_subset': {
            'n': n_hist,
            'auc_with_history': auc_full_h,
            'auc_history_zeroed': auc_zero_h,
            'auc_lift_from_history': round(auc_full_h - auc_zero_h, 5),
            'mean_abs_prob_shift': round(mean_abs_shift_h, 5),
        },
        'note': (
            'Ablation holds the trained RF fixed and zeroes the prior_abxclass__*/'
            'prior_org__* columns at inference (the pre-M3 behaviour). Lift = AUC(with) '
            '- AUC(zeroed). The history-bearing subset is the honest place to read the '
            'effect, since rows with no recorded history are unchanged by zeroing.'
        ),
    }

    out = ec.REPORTS_DIR / 'history_ablation.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')

    print(f"\n  rows with any prior history: {n_hist:,} / {len(X_te):,} "
          f"({result['frac_rows_with_history']*100:.1f}%)")
    print(f"  overall AUC   with={auc_full:.4f}  zeroed={auc_zero:.4f}  "
          f"lift={result['overall']['auc_lift_from_history']:+.4f}")
    print(f"  history subset AUC with={auc_full_h:.4f}  zeroed={auc_zero_h:.4f}  "
          f"lift={result['history_bearing_subset']['auc_lift_from_history']:+.4f}  "
          f"(mean |Δp|={mean_abs_shift_h:.4f})")
    print(f"\n  wrote {out}")


if __name__ == '__main__':
    main()
