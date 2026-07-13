# -*- coding: utf-8 -*-
"""
validate_dosage.py  (M5 / T5.2)
===============================
Audits the guideline dose reference so no drug the system can recommend lands on
an unusable/"unknown" dose, and documents the reference basis.

Checks:
  1. Lookup coverage — rows, distinct generics/diseases/age_groups in dose_route_lookup.csv.
  2. Unusable entries — lookup rows whose dose_range has no numeric value (these are
     precisely why the static guideline default exists; the ML tier is retired).
  3. Recommendable-drug coverage — EVERY US model antibiotic (32) and EVERY drug that
     appears in pakistan.json resolves to a real dose via lookup-or-static-default
     (never 'Consult local formulary', never 'unknown').

Reference basis: the static defaults in DosageService._FALLBACK_DOSING are typical
adult empiric doses per standard references (Sanford Guide / BNF / IDSA syndrome
guidance). They are REFERENCE figures only — not renal/weight-adjusted (see
DOSE_DISCLAIMER). Writes reports/dosage_audit.json.

Run:  python armd_model/validate_dosage.py
"""

import os
import re
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.dosage_service import DosageService, _FALLBACK_DOSING, _CULTURE_SITE_TO_DISEASE  # noqa: E402

REPORTS = ROOT / 'reports'
LOOKUP = ROOT / 'armd_model' / 'artifacts' / 'dose_route_lookup.csv'
PK_FILE = ROOT / 'backend' / 'antibiograms' / 'pakistan.json'

US_MODEL_ANTIBIOTICS = [
    'amikacin', 'ampicillin', 'aztreonam', 'cefazolin', 'cefepime', 'cefotaxime',
    'cefoxitin', 'cefpodoxime', 'ceftazidime', 'ceftriaxone', 'cefuroxime',
    'chloramphenicol', 'ciprofloxacin', 'clarithromycin', 'clindamycin', 'doripenem',
    'doxycycline', 'ertapenem', 'erythromycin', 'fosfomycin', 'gentamicin',
    'levofloxacin', 'linezolid', 'meropenem', 'metronidazole', 'moxifloxacin',
    'nitrofurantoin', 'streptomycin', 'tetracycline', 'tigecycline', 'tobramycin',
    'vancomycin',
]

_HAS_NUMBER = re.compile(r'\d')


def pakistan_drugs():
    if not PK_FILE.exists():
        return []
    data = json.load(open(PK_FILE))
    drugs = set()
    for org in data.get('organisms', {}).values():
        for d in org.get('drugs', {}):
            drugs.add(d.replace('_', ' ').strip().lower())
    return sorted(drugs)


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    svc = DosageService()

    # 1 + 2: lookup coverage / unusable entries
    lookup_stats = {'exists': LOOKUP.exists(), 'entries': len(svc.exact_dose_lookup)}
    unusable = 0
    for (gen, dis, ag), dose in svc.exact_dose_lookup.items():
        if not _HAS_NUMBER.search(str(dose)):
            unusable += 1
    lookup_stats['entries_without_numeric_dose'] = unusable

    # 3: every recommendable drug resolves to a real dose (across all mapped diseases)
    diseases = sorted(set(_CULTURE_SITE_TO_DISEASE.values()))
    all_drugs = sorted(set(US_MODEL_ANTIBIOTICS) | set(pakistan_drugs()))
    unresolved = []
    sample = {}
    for drug in all_drugs:
        ok = True
        for site in _CULTURE_SITE_TO_DISEASE:  # urine/blood/respiratory
            r = svc.get_dosage(drug, site, age=40)
            if not _HAS_NUMBER.search(str(r['dose_range'])):
                ok = False
        # one representative resolution for the report
        rep = svc.get_dosage(drug, 'blood', age=40)
        sample[drug] = f"{rep['dose_range']} {rep['route']} ({rep['source']})"
        if not ok:
            unresolved.append(drug)

    has_static = {d: (d in _FALLBACK_DOSING) for d in all_drugs}
    missing_static = [d for d, ok in has_static.items() if not ok]

    audit = {
        'lookup': lookup_stats,
        'diseases_mapped': diseases,
        'n_recommendable_drugs_checked': len(all_drugs),
        'unresolved_drugs': unresolved,
        'drugs_without_static_default': missing_static,
        'reference_basis': ('Static defaults are typical adult empiric doses per standard '
                            'references (Sanford Guide / BNF / IDSA). Reference figures only — '
                            'not renal/weight-adjusted (see DOSE_DISCLAIMER).'),
        'sample_resolutions': sample,
    }
    out = REPORTS / 'dosage_audit.json'
    json.dump(audit, open(out, 'w'), indent=2)

    print("=" * 60)
    print("M5 — Dosage reference audit")
    print("=" * 60)
    print(f"Lookup entries: {lookup_stats['entries']} "
          f"({unusable} without a numeric dose -> covered by static default)")
    print(f"Recommendable drugs checked: {len(all_drugs)} "
          f"(US {len(US_MODEL_ANTIBIOTICS)} + Pakistan {len(pakistan_drugs())})")
    print(f"Unresolved (no numeric dose anywhere): {unresolved or 'NONE'}")
    print(f"Drugs without a static default: {missing_static or 'NONE'}")
    print("Spot-check (the drugs that previously mis-dosed):")
    for d in ['imipenem', 'azithromycin', 'meropenem', 'colistin']:
        if d in sample:
            print(f"  {d:14s} -> {sample[d]}")
    print(f"\nWrote {out}")
    ok = not unresolved and not missing_static
    print("\nRESULT:", "PASS — every recommendable drug has a real reference dose." if ok
          else "FAIL — see unresolved/missing above.")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
