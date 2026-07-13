# -*- coding: utf-8 -*-
"""
evaluate.py  (M1 — rigorous evaluation)
=======================================
ONE command regenerates every M1 figure + reports/metrics.json:

    python armd_model/evaluate.py

Covers (Review §0, §2 Tier 1):
  T1.1  Per-(organism, drug) AUC/acc/F1 + organism x drug AUC heatmap.
  T1.2  Prevalence + antibiogram baselines and the RF's LIFT over them.
  T1.3  Probability calibration (isotonic + sigmoid): reliability diagram +
        Brier before/after; the calibrated model is saved as the served default.
  T1.4  Coverage-rate-vs-clinician: documented as NOT computable from ARMD
        (no administered/prescribed-drug field) -> Top-k substitute reported.
  T1.5  Top-1 / Top-3 susceptibility hit-rate (honest per-context replacement
        for train_armd.py's brittle exact-match 0.072 metric).
  T1.6  Decision-curve analysis (net benefit vs treat-all / treat-none).

All metrics use the frozen seed-42 patient-grouped split (M0).
"""

import json

import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use('Agg')  # headless / file output
import matplotlib.pyplot as plt

from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, precision_score, recall_score,
    f1_score, brier_score_loss,
)
from sklearn.calibration import CalibratedClassifierCV, calibration_curve

import eval_common as ec
import baselines as bl

MIN_CELL_SUPPORT = 50      # min test rows in an (organism, drug) cell to score its within-cell AUC
MIN_STRATUM_SUPPORT = 100  # min test rows to report a per-organism / per-drug AUC


def _jsonable(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and (np.isnan(o)):
        return None
    raise TypeError(f"not JSON serializable: {type(o)}")


def overall_block(y, p):
    pred = (p >= 0.5).astype(int)
    return {
        'roc_auc': ec.safe_auc(y, p),
        'accuracy': float(accuracy_score(y, pred)),
        'balanced_accuracy': float(balanced_accuracy_score(y, pred)),
        'precision_susceptible': float(precision_score(y, pred, zero_division=0)),
        'recall_susceptible': float(recall_score(y, pred, zero_division=0)),
        'f1_susceptible': float(f1_score(y, pred, zero_division=0)),
        'brier': float(brier_score_loss(y, p)),
        'n': int(len(y)),
    }


def per_stratum_auc(X_test, y_test, p_rf, p_anti, p_prev, by):
    """AUC per organism (by='organism') or per drug (by='antibiotic')."""
    rows = []
    col = X_test[by].astype(str).to_numpy()
    y_arr = y_test.to_numpy()
    for val in pd.unique(col):
        m = col == val
        n = int(m.sum())
        if n < MIN_STRATUM_SUPPORT:
            continue
        yv = y_arr[m]
        rows.append({
            by: val,
            'n': n,
            'pos_rate': float(np.mean(yv)),
            'rf_auc': ec.safe_auc(yv, p_rf[m]),
            'antibiogram_auc': ec.safe_auc(yv, p_anti[m]),
            'prevalence_auc': ec.safe_auc(yv, p_prev[m]),
        })
    rows.sort(key=lambda r: r['n'], reverse=True)
    return rows


def per_cell(X_test, y_test, p_rf):
    """Within-(organism, drug) RF AUC. The antibiogram baseline is CONSTANT in a
    cell (AUC = 0.5 by construction), so cell AUC - 0.5 IS the RF's patient-level
    lift over the antibiogram — the core M1 measurement (Review §0)."""
    org = X_test['organism'].astype(str).to_numpy()
    drug = X_test['antibiotic'].astype(str).to_numpy()
    yv = y_test.to_numpy()
    cells = {}
    for o, d, y_, s in zip(org, drug, yv, p_rf):
        cells.setdefault((o, d), [[], []])
        cells[(o, d)][0].append(y_)
        cells[(o, d)][1].append(s)
    records = []
    for (o, d), (ys, ss) in cells.items():
        if len(ys) < MIN_CELL_SUPPORT:
            continue
        auc = ec.safe_auc(ys, ss)
        if np.isnan(auc):
            continue
        records.append({'organism': o, 'antibiotic': d, 'n': len(ys),
                        'pos_rate': float(np.mean(ys)), 'rf_auc': auc,
                        'lift_over_antibiogram': auc - 0.5})
    records.sort(key=lambda r: r['n'], reverse=True)
    return records


def top_k_hit_rate(X_test, y_test, p_rf, context_cols):
    """Group test rows into patient-contexts (all features except antibiotic) and
    measure whether the top-ranked drug(s) are actually susceptible."""
    ctx_filled = X_test[context_cols].fillna(-999999.0)
    key = pd.util.hash_pandas_object(ctx_filled, index=False).to_numpy()
    work = pd.DataFrame({'key': key, 'prob': p_rf, 'y': y_test.to_numpy()})

    t1_all = t3_all = n_all = 0
    t1_inf = t3_inf = n_inf = 0
    for _, g in work.groupby('key', sort=False):
        g = g.sort_values('prob', ascending=False)
        yv = g['y'].values
        top1 = int(yv[0] == 1)
        top3 = int((yv[:3] == 1).any())
        n_all += 1
        t1_all += top1
        t3_all += top3
        if (yv == 0).any() and (yv == 1).any():  # informative: has >=1 R and >=1 S
            n_inf += 1
            t1_inf += top1
            t3_inf += top3
    return {
        'n_contexts': n_all,
        'top1_hit_rate_all': t1_all / n_all if n_all else None,
        'top3_hit_rate_all': t3_all / n_all if n_all else None,
        'n_informative_contexts': n_inf,
        'top1_hit_rate_informative': t1_inf / n_inf if n_inf else None,
        'top3_hit_rate_informative': t3_inf / n_inf if n_inf else None,
        'note': ('Informative contexts have >=1 resistant AND >=1 susceptible tested drug — '
                 'the discriminating case where ranking actually matters.'),
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_per_organism_auc(per_org, path):
    top = per_org[:15]
    labels = [r['organism'][:22] for r in top]
    rf = [r['rf_auc'] for r in top]
    anti = [r['antibiogram_auc'] for r in top]
    x = np.arange(len(top))
    w = 0.38
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(x - w / 2, rf, w, label='RandomForest', color='#2563eb')
    ax.bar(x + w / 2, anti, w, label='Antibiogram baseline', color='#f59e0b')
    ax.axhline(0.5, ls='--', c='gray', lw=1, label='chance (0.5)')
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('ROC-AUC'); ax.set_ylim(0.4, 1.0)
    ax.set_title('Per-organism AUC: RF vs antibiogram baseline (top 15 by test support)')
    ax.legend(); fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def fig_cell_heatmap(cell_records, path):
    orgs = sorted({r['organism'] for r in cell_records})
    drugs = sorted({r['antibiotic'] for r in cell_records})
    if not orgs or not drugs:
        return
    M = np.full((len(orgs), len(drugs)), np.nan)
    oi = {o: i for i, o in enumerate(orgs)}
    di = {d: j for j, d in enumerate(drugs)}
    for r in cell_records:
        M[oi[r['organism']], di[r['antibiotic']]] = r['rf_auc']
    fig, ax = plt.subplots(figsize=(min(0.42 * len(drugs) + 4, 20), min(0.42 * len(orgs) + 3, 22)))
    im = ax.imshow(M, aspect='auto', cmap='RdYlGn', vmin=0.4, vmax=0.9)
    ax.set_xticks(range(len(drugs))); ax.set_xticklabels(drugs, rotation=90, fontsize=7)
    ax.set_yticks(range(len(orgs))); ax.set_yticklabels(orgs, fontsize=7)
    ax.set_title('Within-(organism x drug) RF AUC  (0.5 = no lift over antibiogram)')
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label='RF within-cell AUC')
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def fig_reliability(y, p_uncal, p_iso, path):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], 'k--', lw=1, label='perfectly calibrated')
    for p, name, c in [(p_uncal, 'uncalibrated RF', '#ef4444'), (p_iso, 'isotonic', '#2563eb')]:
        frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy='quantile')
        ax.plot(mean_pred, frac_pos, marker='o', label=name, color=c)
    ax.set_xlabel('mean predicted P(susceptible)'); ax.set_ylabel('observed fraction susceptible')
    ax.set_title('Reliability diagram (test set)'); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def fig_decision_curve(y, p, path):
    y = np.asarray(y)
    N = len(y)
    prev = y.mean()
    pts = np.linspace(0.01, 0.6, 60)
    nb_model, nb_all = [], []
    for pt in pts:
        pred = (p >= pt).astype(int)
        tp = np.sum((pred == 1) & (y == 1))
        fp = np.sum((pred == 1) & (y == 0))
        w = pt / (1 - pt)
        nb_model.append(tp / N - fp / N * w)
        nb_all.append(prev - (1 - prev) * w)  # treat everyone
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(pts, nb_model, label='AURA model', color='#2563eb', lw=2)
    ax.plot(pts, nb_all, label='treat all', color='#f59e0b', lw=1.2)
    ax.axhline(0, color='gray', lw=1, label='treat none')
    ax.set_xlabel('threshold probability'); ax.set_ylabel('net benefit')
    ax.set_ylim(bottom=min(0, min(nb_model)) - 0.02)
    ax.set_title('Decision-curve analysis (test set)'); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    ec.ensure_dirs()
    print("=" * 60)
    print("M1 — Rigorous evaluation")
    print("=" * 60)

    data = ec.reconstruct_splits()
    model = ec.load_model()
    X_tr, y_tr = data['X_train'], data['y_train']
    X_va, y_va = data['X_val'], data['y_val']
    X_te, y_te = data['X_test'], data['y_test']
    feature_cols = data['feature_cols']

    print("\n[1] Scoring RF on validation + test...")
    p_te = model.predict_proba(X_te)[:, 1]
    p_va = model.predict_proba(X_va)[:, 1]

    rf_overall = overall_block(y_te, p_te)
    print(f"    RF test AUC={rf_overall['roc_auc']:.4f} acc={rf_overall['accuracy']:.4f} "
          f"F1={rf_overall['f1_susceptible']:.4f} Brier={rf_overall['brier']:.4f}")
    # sanity vs M0 baseline
    assert abs(rf_overall['roc_auc'] - 0.851) < 0.01, "RF AUC drifted from frozen baseline!"

    print("[2] Fitting baselines (prevalence + antibiogram) on TRAIN...")
    prev_tbl = bl.fit_prevalence(X_tr, y_tr)
    cell_tbl, prev_tbl2, anti_stats = bl.fit_antibiogram(X_tr, y_tr, min_isolates=30)
    p_prev = bl.score_prevalence(X_te, prev_tbl)
    p_anti = bl.score_antibiogram(X_te, cell_tbl, prev_tbl2)
    prev_auc = ec.safe_auc(y_te, p_prev)
    anti_auc = ec.safe_auc(y_te, p_anti)
    print(f"    overall AUC  RF={rf_overall['roc_auc']:.4f}  antibiogram={anti_auc:.4f}  prevalence={prev_auc:.4f}")

    print("[3] Per-organism / per-drug stratified AUC (T1.1)...")
    per_org = per_stratum_auc(X_te, y_te, p_te, p_anti, p_prev, 'organism')
    per_drug = per_stratum_auc(X_te, y_te, p_te, p_anti, p_prev, 'antibiotic')

    print("[4] Per-(organism x drug) within-cell AUC / lift (T1.1)...")
    cells = per_cell(X_te, y_te, p_te)
    cell_aucs = np.array([c['rf_auc'] for c in cells]) if cells else np.array([])
    cell_summary = {
        'n_cells_evaluated': len(cells),
        'min_cell_support': MIN_CELL_SUPPORT,
        'median_rf_cell_auc': float(np.median(cell_aucs)) if len(cell_aucs) else None,
        'mean_rf_cell_auc': float(np.mean(cell_aucs)) if len(cell_aucs) else None,
        'frac_cells_auc_gt_0_55': float(np.mean(cell_aucs > 0.55)) if len(cell_aucs) else None,
        'frac_cells_auc_gt_0_60': float(np.mean(cell_aucs > 0.60)) if len(cell_aucs) else None,
        'interpretation': ('Within a cell the antibiogram is constant (AUC=0.5); cell AUC>0.5 is the '
                           'RF patient-specific lift. Median near 0.5 => little lift over the antibiogram.'),
    }
    print(f"    cells={cell_summary['n_cells_evaluated']} median cell AUC="
          f"{cell_summary['median_rf_cell_auc']}  frac>0.55={cell_summary['frac_cells_auc_gt_0_55']}")

    print("[5] Top-k susceptibility hit-rate (T1.5)...")
    context_cols = [c for c in feature_cols if c != 'antibiotic']
    topk = top_k_hit_rate(X_te, y_te, p_te, context_cols)
    print(f"    Top-1(all)={topk['top1_hit_rate_all']:.3f}  Top-3(all)={topk['top3_hit_rate_all']:.3f}  "
          f"| informative n={topk['n_informative_contexts']} "
          f"Top-1={topk['top1_hit_rate_informative']:.3f} Top-3={topk['top3_hit_rate_informative']:.3f}")

    print("[6] Calibration (T1.3): fitting isotonic + sigmoid on VAL (cv=prefit)...")
    cal_iso = CalibratedClassifierCV(model, cv='prefit', method='isotonic').fit(X_va, y_va)
    cal_sig = CalibratedClassifierCV(model, cv='prefit', method='sigmoid').fit(X_va, y_va)
    p_iso = cal_iso.predict_proba(X_te)[:, 1]
    p_sig = cal_sig.predict_proba(X_te)[:, 1]
    calibration = {
        'brier_uncalibrated': float(brier_score_loss(y_te, p_te)),
        'brier_isotonic': float(brier_score_loss(y_te, p_iso)),
        'brier_sigmoid': float(brier_score_loss(y_te, p_sig)),
        'served_method': 'isotonic',
        'note': ('Isotonic is monotonic non-decreasing, so it preserves the RF score ORDER within '
                 'a request -> Top-k rankings are unchanged; only the probability VALUES become '
                 'decision-grade. Shipped as rf_top3_recommender_calibrated.joblib.'),
    }
    print(f"    Brier  uncal={calibration['brier_uncalibrated']:.4f}  "
          f"isotonic={calibration['brier_isotonic']:.4f}  sigmoid={calibration['brier_sigmoid']:.4f}")

    # Save calibrated model as the served default (T1.3 / wired into predictor separately).
    cal_path = ec.ARTIFACT_DIR / 'rf_top3_recommender_calibrated.joblib'
    joblib.dump(cal_iso, cal_path, compress=3)
    size_mb = cal_path.stat().st_size / 1e6
    print(f"    Saved calibrated model -> {cal_path.name} ({size_mb:.1f} MB)")
    assert size_mb < 100, "Calibrated artifact exceeds 100 MB GitHub limit!"

    print("[7] Figures...")
    fig_per_organism_auc(per_org, ec.FIG_DIR / 'per_organism_auc.png')
    fig_cell_heatmap(cells, ec.FIG_DIR / 'organism_drug_auc_heatmap.png')
    fig_reliability(y_te, p_te, p_iso, ec.FIG_DIR / 'calibration_reliability.png')
    fig_decision_curve(y_te, p_iso, ec.FIG_DIR / 'decision_curve.png')

    metrics = {
        'meta': {
            'seed': data['manifest']['random_state'],
            'n_test_rows': int(len(y_te)),
            'n_test_patients': data['manifest']['n_patients']['test'],
            'antibiogram_min_isolates': 30,
            'coverage_rate_vs_clinician': (
                'NOT COMPUTABLE from ARMD: the cohort records the TESTED antibiotic + susceptibility '
                'result, not the drug the clinician actually administered (no prescribed-drug field). '
                'Per roadmap T1.4, Top-k susceptibility hit-rate is reported as the substitute.'),
        },
        'overall': {
            'rf': rf_overall,
            'antibiogram_baseline_auc': anti_auc,
            'prevalence_baseline_auc': prev_auc,
            'rf_lift_over_antibiogram_auc': (rf_overall['roc_auc'] - anti_auc
                                             if not np.isnan(anti_auc) else None),
        },
        'per_organism': per_org,
        'per_drug': per_drug,
        'per_cell_summary': cell_summary,
        'per_cell_top': cells[:40],
        'top_k': topk,
        'calibration': calibration,
        'baselines_meta': anti_stats,
        'figures': [
            'reports/figures/per_organism_auc.png',
            'reports/figures/organism_drug_auc_heatmap.png',
            'reports/figures/calibration_reliability.png',
            'reports/figures/decision_curve.png',
        ],
    }
    out = ec.REPORTS_DIR / 'metrics.json'
    with open(out, 'w') as f:
        json.dump(metrics, f, indent=2, default=_jsonable)
    print(f"\nWrote {out}")
    print(f"Figures -> {ec.FIG_DIR}")
    print("\nM1 evaluation complete.")


if __name__ == '__main__':
    main()
