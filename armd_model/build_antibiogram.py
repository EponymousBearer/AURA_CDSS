# -*- coding: utf-8 -*-
"""
Build an organism -> allowed-antibiotics panel (antibiogram) from the ARMD cohort.

An antibiotic is "allowed" for an organism if the (organism, antibiotic) pair was
tested at least MIN_ISOLATES times in the cohort (CLSI M39 recommends >= 30 isolates
for antibiogram reporting). This is the clinical candidate filter used at inference:
drugs a lab never tests for an organism (e.g. metronidazole vs E. coli) are excluded.

Reads : <project_root>/datasets/microbiology_cultures_cohort.csv
Writes: <project_root>/armd_model/artifacts/organism_antibiotic_panel.json
"""

import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent.parent / 'datasets'
ARTIFACT_DIR = Path(__file__).parent / 'artifacts'
COHORT = BASE_DIR / 'microbiology_cultures_cohort.csv'

MIN_ISOLATES = 30  # CLSI M39 minimum for antibiogram reporting

SELECTED_ANTIBIOTICS = [
    'amikacin', 'ampicillin', 'aztreonam', 'cefazolin', 'cefepime', 'cefotaxime',
    'cefoxitin', 'cefpodoxime', 'ceftazidime', 'ceftriaxone', 'cefuroxime',
    'chloramphenicol', 'ciprofloxacin', 'clarithromycin', 'clindamycin', 'doripenem',
    'doxycycline', 'ertapenem', 'erythromycin', 'fosfomycin', 'gentamicin',
    'levofloxacin', 'linezolid', 'meropenem', 'metronidazole', 'moxifloxacin',
    'nitrofurantoin', 'streptomycin', 'tetracycline', 'tigecycline', 'tobramycin',
    'vancomycin',
]


def normalize_antibiotic_name(x):
    if pd.isna(x):
        return None
    x = str(x).strip().lower().replace('_', ' ').replace('-', ' ')
    return ' '.join(x.split())


def map_susceptibility(value):
    if pd.isna(value):
        return None
    s = str(value).strip().lower()
    if s in {'susceptible', 's', 'sus'}:
        return 1
    if s in {'resistant', 'r', 'res'}:
        return 0
    return None


def main():
    print(f"Reading cohort: {COHORT}")
    df = pd.read_csv(
        COHORT,
        usecols=['organism', 'antibiotic', 'susceptibility', 'was_positive'],
        dtype='string',
        low_memory=False,
    )

    # mirror the training filter: positive cultures, selected antibiotics, S/R only
    pos = {'1', 'true', 't', 'yes', 'y', 'positive'}
    df['was_positive'] = df['was_positive'].str.strip().str.lower()
    df = df[df['was_positive'].isin(pos)]

    df['antibiotic'] = df['antibiotic'].map(normalize_antibiotic_name)
    df = df[df['antibiotic'].isin(SELECTED_ANTIBIOTICS)]

    df['organism'] = df['organism'].str.strip().str.lower()
    df['target'] = df['susceptibility'].map(map_susceptibility)
    df = df.dropna(subset=['organism', 'antibiotic', 'target'])

    grp = (
        df.groupby(['organism', 'antibiotic'])['target']
        .agg(n_tested='count', n_sus='sum')
        .reset_index()
    )
    grp['pct_sus'] = (grp['n_sus'] / grp['n_tested']).round(4)

    # distribution of test counts
    print("\nTest-count distribution per (organism, antibiotic) pair:")
    print(grp['n_tested'].describe().round(1).to_string())
    print(f"\nPairs total: {len(grp):,}  | pairs with n_tested >= {MIN_ISOLATES}: "
          f"{(grp['n_tested'] >= MIN_ISOLATES).sum():,}")

    allowed = grp[grp['n_tested'] >= MIN_ISOLATES]

    panel = {}
    stats = {}
    for org, sub in allowed.groupby('organism'):
        sub = sub.sort_values('n_tested', ascending=False)
        panel[org] = sub['antibiotic'].tolist()
        stats[org] = {
            r['antibiotic']: {'n_tested': int(r['n_tested']), 'pct_sus': float(r['pct_sus'])}
            for _, r in sub.iterrows()
        }

    out = {
        'min_isolates': MIN_ISOLATES,
        'source': 'microbiology_cultures_cohort.csv',
        'note': 'organism -> antibiotics tested >= min_isolates times (CLSI M39 antibiogram rule)',
        'panel': panel,
        'stats': stats,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / 'organism_antibiotic_panel.json').write_text(json.dumps(out, indent=2))
    print(f"\nSaved panel for {len(panel)} organisms -> {ARTIFACT_DIR / 'organism_antibiotic_panel.json'}")

    # panel size distribution
    sizes = pd.Series({o: len(v) for o, v in panel.items()})
    print(f"\nPanel size (allowed antibiotics) per organism: "
          f"min={sizes.min()}, median={int(sizes.median())}, max={sizes.max()}")

    # show a few key organisms
    print("\nSample panels (allowed antibiotics, sorted by isolates tested):")
    for org in ['escherichia coli', 'pseudomonas aeruginosa', 'staphylococcus aureus',
                'enterococcus species', 'klebsiella pneumoniae']:
        if org in panel:
            print(f"\n  {org}  ({len(panel[org])} drugs):")
            for ab in panel[org]:
                st = stats[org][ab]
                print(f"      {ab:16s}  n={st['n_tested']:>6}  %S={st['pct_sus']*100:5.1f}")
        else:
            print(f"\n  {org}: NOT in panel (no pair >= {MIN_ISOLATES} isolates)")


if __name__ == '__main__':
    main()
