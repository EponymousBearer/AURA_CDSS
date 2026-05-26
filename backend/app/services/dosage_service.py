"""
Dosage prediction service for v2.
Uses a hybrid approach: exact lookup from the cleaned training table first,
then ML RandomForest fallback for unseen (antibiotic, disease, age_group) combinations.
Falls back to a static rules table if no trained artifacts are found.
"""

import os
import logging
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# The recommender works in culture SITES (urine/blood/respiratory) but the dose
# table is keyed by clinical DISEASE. Map each site to its best-covered disease in
# dose_route_lookup.csv so exact dose lookups actually hit (chosen by antibiotic
# coverage: UTI=19 drugs, Bacteremia=12, Pneumonia=23, all across child/adult/elderly).
_CULTURE_SITE_TO_DISEASE: dict[str, str] = {
    'urine': 'Urinary Tract Infection',
    'blood': 'Bacteremia',
    'respiratory': 'Pneumonia',
}

# Static fallback dosing rules (used if artifacts not trained yet)
_FALLBACK_DOSING: dict[str, dict] = {
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

            dose_path = artifacts_dir / 'dose_model_hybrid.pkl'
            route_path = artifacts_dir / 'route_model_hybrid.pkl'
            if dose_path.exists() and route_path.exists():
                self.dose_model = joblib.load(dose_path)
                self.route_model = joblib.load(route_path)
                logger.info("Dosage ML models loaded")

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

        static = _FALLBACK_DOSING.get(ab_norm, {'dose_range': 'Consult pharmacy', 'route': 'IV'})

        # 1. Exact lookup (preferred — but only when it carries a real dose/route)
        look_dose = self.exact_dose_lookup.get(key)
        look_route = self.exact_route_lookup.get(key)

        # 2. ML model — only run if the lookup is missing or unusable
        ml_dose = ml_route = None
        if (not _usable(look_dose) or not _usable(look_route)) and self.dose_model is not None:
            try:
                input_df = pd.DataFrame([{
                    'generic': ab_norm,
                    'disease': disease_mapped,
                    'age_group': ag,
                }])
                ml_dose = str(self.dose_model.predict(input_df)[0])
                ml_route = str(self.route_model.predict(input_df)[0])
            except Exception as exc:
                logger.warning(f"Dosage ML model failed for {antibiotic}: {exc}")

        # Resolve dose and route independently, never surfacing 'unknown'.
        if _usable(look_dose):
            dose, source = look_dose, 'lookup'
        elif _usable(ml_dose):
            dose, source = ml_dose, 'model'
        else:
            dose, source = static['dose_range'], 'fallback'

        if _usable(look_route):
            route = look_route
        elif _usable(ml_route):
            route = ml_route
        else:
            route = static['route']

        return {'dose_range': dose, 'route': route, 'source': source}

    def get_model_info(self) -> dict:
        return {
            'model_type': 'Hybrid lookup + RandomForest fallback',
            'available': self.dose_model is not None and self.route_model is not None,
            'lookup_entries': len(self.exact_dose_lookup),
            'fallback_antibiotics': len(_FALLBACK_DOSING),
            'artifacts': {
                'lookup_table': 'dose_route_lookup.csv',
                'dose_model': 'dose_model_hybrid.pkl',
                'route_model': 'route_model_hybrid.pkl',
            },
        }
