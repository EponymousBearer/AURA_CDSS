"""
Dosage reference service for v2.

SCOPE (M5 — honest reframe): this is a **guideline dose reference**, NOT a validated
dosing engine. It resolves a standard adult/paediatric dose via:
  1. an exact lookup in dose_route_lookup.csv (guideline table), then
  2. a static per-drug guideline default.
It does NOT perform pharmacokinetic, renal, weight-based, or interaction-aware dosing.
The ML dose/route RandomForest that previously filled gaps has been **retired** from
the resolution path: predicting free-text dose strings with a tree model produced
implausible values (e.g. "30-40 mg" for a carbapenem) and is not defensible as dosing.
Every dose is a reference figure to be confirmed against a local formulary.
"""

import os
import logging
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Shown wherever a dose is surfaced. Keeps the research-only, not-a-medical-device framing.
DOSE_DISCLAIMER = (
    "Doses are standard guideline reference figures (typical adult unless age-banded), "
    "NOT validated or patient-adjusted dosing. Not for clinical use — confirm every dose, "
    "route and interval against a local formulary and adjust for renal function and weight."
)

# The recommender works in culture SITES (urine/blood/respiratory) but the dose
# table is keyed by clinical DISEASE. Map each site to its best-covered disease in
# dose_route_lookup.csv so exact dose lookups actually hit (chosen by antibiotic
# coverage: UTI=19 drugs, Bacteremia=12, Pneumonia=23, all across child/adult/elderly).
_CULTURE_SITE_TO_DISEASE: dict[str, str] = {
    'urine': 'Urinary Tract Infection',
    'blood': 'Bacteremia',
    'respiratory': 'Pneumonia',
}

# Static guideline default doses (typical adult empiric doses; standard references
# such as the Sanford Guide / BNF / IDSA syndrome guidance). Used when the lookup
# table has no usable entry. Keys are lowercase; multi-word agents use spaces to match
# the antibiogram/display naming (e.g. 'trimethoprim sulfamethoxazole'). These are
# REFERENCE figures only (see DOSE_DISCLAIMER) — not renal/weight-adjusted.
_FALLBACK_DOSING: dict[str, dict] = {
    # --- Pakistan-locale / extended agents (not in the US model's 32 but present in
    #     pakistan.json; added so the antibiogram path never lands on 'Consult formulary') ---
    'imipenem':                        {'dose_range': '500 mg',         'route': 'IV'},
    'azithromycin':                    {'dose_range': '500 mg',         'route': 'PO'},
    'colistin':                        {'dose_range': '2.5-5 mg/kg/day', 'route': 'IV'},
    'oxacillin':                       {'dose_range': '1000-2000 mg',   'route': 'IV'},
    'amoxicillin clavulanate':         {'dose_range': '875/125 mg',     'route': 'PO'},
    'piperacillin tazobactam':         {'dose_range': '4.5 g',          'route': 'IV'},
    'ceftazidime avibactam':           {'dose_range': '2.5 g',          'route': 'IV'},
    'trimethoprim sulfamethoxazole':   {'dose_range': '160/800 mg',     'route': 'PO'},
    # --- US model's 32 antibiotics ---
    'amikacin':       {'dose_range': '15-20 mg/kg',        'route': 'IV'},
    'ampicillin':     {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'aztreonam':      {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefazolin':      {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefepime':       {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefotaxime':     {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefoxitin':      {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefpodoxime':    {'dose_range': '200-400 mg',          'route': 'PO'},
    'ceftazidime':    {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'ceftriaxone':    {'dose_range': '1000-2000 mg',        'route': 'IV'},
    'cefuroxime':     {'dose_range': '750-1500 mg',         'route': 'IV'},
    'chloramphenicol':{'dose_range': '500-1000 mg',         'route': 'IV'},
    'ciprofloxacin':  {'dose_range': '400 mg',              'route': 'IV'},
    'clarithromycin': {'dose_range': '500 mg',              'route': 'PO'},
    'clindamycin':    {'dose_range': '600-900 mg',          'route': 'IV'},
    'doripenem':      {'dose_range': '500-1000 mg',         'route': 'IV'},
    'doxycycline':    {'dose_range': '100-200 mg',          'route': 'PO'},
    'ertapenem':      {'dose_range': '1000 mg',             'route': 'IV'},
    'erythromycin':   {'dose_range': '500-1000 mg',         'route': 'PO'},
    'fosfomycin':     {'dose_range': '3000 mg',             'route': 'PO'},
    'gentamicin':     {'dose_range': '5-7 mg/kg',           'route': 'IV'},
    'levofloxacin':   {'dose_range': '500-750 mg',          'route': 'IV'},
    'linezolid':      {'dose_range': '600 mg',              'route': 'IV'},
    'meropenem':      {'dose_range': '500-1000 mg',         'route': 'IV'},
    'metronidazole':  {'dose_range': '500 mg',              'route': 'IV'},
    'moxifloxacin':   {'dose_range': '400 mg',              'route': 'IV'},
    'nitrofurantoin': {'dose_range': '100 mg',              'route': 'PO'},
    'streptomycin':   {'dose_range': '15 mg/kg',            'route': 'IM'},
    'tetracycline':   {'dose_range': '250-500 mg',          'route': 'PO'},
    'tigecycline':    {'dose_range': '100 mg load / 50 mg', 'route': 'IV'},
    'tobramycin':     {'dose_range': '5-7 mg/kg',           'route': 'IV'},
    'vancomycin':     {'dose_range': '15-20 mg/kg',         'route': 'IV'},
}


class DosageService:
    """
    Hybrid dosage predictor.
    Priority: exact lookup -> ML model -> static rules fallback.
    """

    def __init__(self):
        self.exact_dose_lookup: dict = {}
        self.exact_route_lookup: dict = {}
        self.dose_model = None
        self.route_model = None
        self._load_artifacts()

    def _resolve_artifacts_dir(self) -> Path:
        env_path = os.getenv('ARMD_ARTIFACTS_DIR')
        if env_path:
            return Path(env_path)
        this_file = Path(__file__).resolve()
        project_root = this_file.parent.parent.parent.parent
        return project_root / 'armd_model' / 'artifacts'

    def _load_artifacts(self):
        artifacts_dir = self._resolve_artifacts_dir()

        try:
            lookup_path = artifacts_dir / 'dose_route_lookup.csv'
            if lookup_path.exists():
                lookup_df = pd.read_csv(lookup_path)
                # Keys are lowercased so they match the normalized lookup key built
                # in get_dosage (the CSV stores Title-Case disease names).
                self.exact_dose_lookup = {
                    (str(r['generic']).strip().lower(),
                     str(r['disease']).strip().lower(),
                     str(r['age_group']).strip().lower()): str(r['dose_range'])
                    for _, r in lookup_df.iterrows()
                }
                self.exact_route_lookup = {
                    (str(r['generic']).strip().lower(),
                     str(r['disease']).strip().lower(),
                     str(r['age_group']).strip().lower()): str(r['route'])
                    for _, r in lookup_df.iterrows()
                }
                logger.info(f"Dosage lookup table loaded: {len(self.exact_dose_lookup)} entries")

            # ML dose/route models are RETIRED (M5): not loaded, not used. Predicting
            # free-text dose strings with a tree model isn't defensible as dosing.
            # dose_model_hybrid.pkl / route_model_hybrid.pkl remain on disk for the
            # record but are intentionally not loaded (also saves RAM on the 512 MB host).

        except Exception as exc:
            logger.warning(f"Could not load dosage artifacts: {exc}. Using static rules fallback.")

    def _age_group(self, age: int) -> str:
        if age < 12:
            return 'child'
        if age < 65:
            return 'adult'
        return 'elderly'

    def get_dosage(self, antibiotic: str, disease: str, age: int) -> dict:
        """
        Returns {'dose_range': str, 'route': str, 'source': str}
        source is one of: 'lookup', 'model', 'fallback'
        """
        ab_norm = antibiotic.strip().lower()
        # Translate culture site -> disease (Title-Case preserved for the ML model,
        # which was trained on the CSV's disease casing); lowercased copy for lookup.
        disease_mapped = _CULTURE_SITE_TO_DISEASE.get(disease.strip().lower(), disease)
        ag = self._age_group(age)
        key = (ab_norm, disease_mapped.strip().lower(), ag)

        def _usable(v) -> bool:
            # Many d_dose rows carry a route but no numeric dose -> 'unknown'.
            return v is not None and str(v).strip().lower() not in {'unknown', 'nan', '', 'none'}

        static = _FALLBACK_DOSING.get(ab_norm, {'dose_range': 'Consult local formulary', 'route': 'IV'})

        # Resolution is now guideline-reference only (M5): exact lookup, else the static
        # guideline default. The ML dose/route model is NOT consulted — see module docstring.
        look_dose = self.exact_dose_lookup.get(key)
        look_route = self.exact_route_lookup.get(key)

        # 1. Exact guideline lookup (preferred — only when it carries a real dose/route)
        if _usable(look_dose):
            dose, source = look_dose, 'lookup'
        else:
            # 2. Static guideline default (clearly a default, never 'unknown')
            dose, source = static['dose_range'], 'fallback'

        route = look_route if _usable(look_route) else static['route']

        return {'dose_range': dose, 'route': route, 'source': source, 'disclaimer': DOSE_DISCLAIMER}

    def get_model_info(self) -> dict:
        return {
            'model_type': 'Guideline dose reference (lookup table + static defaults)',
            'validated': False,
            'disclaimer': DOSE_DISCLAIMER,
            # The dose reference is always available (static guideline defaults cover
            # every recommendable drug even if the lookup CSV is missing).
            'available': True,
            'lookup_entries': len(self.exact_dose_lookup),
            'fallback_antibiotics': len(_FALLBACK_DOSING),
            'ml_dosing': 'retired — RandomForest dose/route model is no longer used for recommendations',
            'artifacts': {
                'lookup_table': 'dose_route_lookup.csv',
                'dose_model': 'dose_model_hybrid.pkl (retired)',
                'route_model': 'route_model_hybrid.pkl (retired)',
            },
        }
