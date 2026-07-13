# -*- coding: utf-8 -*-
"""
baselines.py  (M1 / T1.2)
=========================
The two baselines every ML claim on this task must beat (Review §0, §2 Tier 1):

  (a) PREVALENCE baseline   -> predict each drug's overall %-susceptible
                               (ignores organism and patient entirely).
  (b) ANTIBIOGRAM baseline  -> predict the local %-susceptible for that
                               (organism, drug) cell from TRAINING data.
                               This is the clinical standard of care (CLSI M39)
                               and AURA's real competitor.

Both are fit on the TRAIN split only and scored on TEST, so the comparison is
honest. The antibiogram baseline is constant within a single (organism, drug)
cell -> it has NO within-cell discrimination (AUC = 0.5 by construction). That
is exactly why per-(organism, drug) RF AUC (evaluate.py, T1.1) measures the
patient-specific lift the RF adds *over* the antibiogram.
"""

import numpy as np


GLOBAL_KEY = '__global__'


def fit_prevalence(X_train, y_train):
    """drug -> P(susceptible) over the whole training set."""
    import pandas as pd
    s = pd.Series(np.asarray(y_train), index=X_train['antibiotic'].values)
    table = s.groupby(level=0).mean().to_dict()
    table[GLOBAL_KEY] = float(np.mean(y_train))
    return table


def score_prevalence(X, table):
    g = table[GLOBAL_KEY]
    return X['antibiotic'].map(lambda d: table.get(d, g)).astype(float).values


def fit_antibiogram(X_train, y_train, min_isolates: int = 30):
    """(organism, drug) -> P(susceptible) from training data, CLSI M39 style.

    Cells with < min_isolates fall back to the drug-level prevalence, then the
    global rate. Returns (cell_table, prevalence_table, coverage_stats).
    """
    import pandas as pd
    df = pd.DataFrame({
        'organism': X_train['organism'].values,
        'antibiotic': X_train['antibiotic'].values,
        'y': np.asarray(y_train),
    })
    grp = df.groupby(['organism', 'antibiotic'])['y'].agg(['mean', 'size'])
    cell = {
        (org, drug): float(row['mean'])
        for (org, drug), row in grp.iterrows()
        if row['size'] >= min_isolates
    }
    prevalence = fit_prevalence(X_train, y_train)
    stats = {
        'n_cells_total': int(grp.shape[0]),
        'n_cells_reportable': len(cell),
        'min_isolates': min_isolates,
    }
    return cell, prevalence, stats


def score_antibiogram(X, cell_table, prevalence_table):
    g = prevalence_table[GLOBAL_KEY]
    orgs = X['organism'].values
    drugs = X['antibiotic'].values
    out = np.empty(len(X), dtype=float)
    for i, (o, d) in enumerate(zip(orgs, drugs)):
        v = cell_table.get((o, d))
        if v is None:
            v = prevalence_table.get(d, g)
        out[i] = v
    return out
