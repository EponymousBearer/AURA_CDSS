"""
ARMD RandomForest prediction service for v2 antibiotic recommendations.
Loads the trained sklearn Pipeline (preprocessor + RandomForest) and
scores all 32 candidate antibiotics per patient context.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SELECTED_ANTIBIOTICS = [
    'amikacin', 'ampicillin', 'aztreonam', 'cefazolin', 'cefepime', 'cefotaxime',
    'cefoxitin', 'cefpodoxime', 'ceftazidime', 'ceftriaxone', 'cefuroxime',
    'chloramphenicol', 'ciprofloxacin', 'clarithromycin', 'clindamycin', 'doripenem',
    'doxycycline', 'ertapenem', 'erythromycin', 'fosfomycin', 'gentamicin',
    'levofloxacin', 'linezolid', 'meropenem', 'metronidazole', 'moxifloxacin',
    'nitrofurantoin', 'streptomycin', 'tetracycline', 'tigecycline', 'tobramycin',
    'vancomycin',
]


class ARMDPredictorService:
    """
    Loads the trained ARMD RandomForest pipeline and provides top-3 antibiotic
    susceptibility predictions given a patient context.

    At inference we score all candidate antibiotics by injecting each one as the
    'antibiotic' feature into the patient feature row, running predict_proba, and
    ranking by P(susceptible=1).
    """

    def __init__(self):
        self.model = None
        self.feature_cols: list[str] = []
        self.selected_antibiotics: list[str] = SELECTED_ANTIBIOTICS
        self.best_threshold: float = 0.5
        self.metadata: dict = {}
        self.test_summary: list[dict] = []
        self.feature_importances: list[dict] = []
        self._load_artifacts()

    def _resolve_artifacts_dir(self) -> Path:
        env_path = os.getenv('ARMD_ARTIFACTS_DIR')
        if env_path:
            return Path(env_path)
        # Default: look two levels up from this file (backend/app/services -> project root)
        # then into armd_model/artifacts
        this_file = Path(__file__).resolve()
        project_root = this_file.parent.parent.parent.parent
        return project_root / 'armd_model' / 'artifacts'

    def _load_artifacts(self):
        artifacts_dir = self._resolve_artifacts_dir()
        logger.info(f"Looking for ARMD artifacts in: {artifacts_dir}")

        try:
            self.model = joblib.load(artifacts_dir / 'rf_top3_recommender_optimized.joblib')
            self.feature_cols = joblib.load(artifacts_dir / 'feature_cols.joblib')
            self.best_threshold = float(joblib.load(artifacts_dir / 'best_threshold.joblib'))

            ab_path = artifacts_dir / 'selected_antibiotics.joblib'
            if ab_path.exists():
                self.selected_antibiotics = joblib.load(ab_path)

            meta_path = artifacts_dir / 'metadata_optimized.json'
            if meta_path.exists():
                with open(meta_path) as f:
                    self.metadata = json.load(f)

            summary_path = artifacts_dir / 'split_test_summary.joblib'
            if summary_path.exists():
                summary_df = joblib.load(summary_path)
                self.test_summary = [
                    {
                        key: round(float(value), 6) if isinstance(value, (int, float, np.floating)) else value
                        for key, value in row.items()
                    }
                    for row in summary_df.to_dict(orient='records')
                ]

            importances_path = artifacts_dir / 'feature_importances.joblib'
            if importances_path.exists():
                importances_df = joblib.load(importances_path)
                self.feature_importances = [
                    {
                        'feature': str(row['feature']),
                        'importance': round(float(row['importance']), 6),
                    }
                    for _, row in importances_df.head(10).iterrows()
                ]

            logger.info(
                f"ARMD model loaded. antibiotics={len(self.selected_antibiotics)} "
                f"features={len(self.feature_cols)} threshold={self.best_threshold:.3f}"
            )
        except FileNotFoundError as exc:
            logger.warning(
                f"ARMD model artifacts not found ({exc}). "
                "Run armd_model/train_armd.py first to generate them."
            )
        except Exception as exc:
            logger.error(f"Failed to load ARMD model: {exc}", exc_info=True)

    def is_available(self) -> bool:
        return self.model is not None and len(self.feature_cols) > 0

    def _normalize(self, value: Optional[str]) -> str:
        if value is None:
            return 'unknown'
        return str(value).strip().lower()

    def predict(
        self,
        culture_description: str,
        organism: str,
        age: int,
        gender: str,
        wbc: Optional[float] = None,
        cr: Optional[float] = None,
        lactate: Optional[float] = None,
        procalcitonin: Optional[float] = None,
        ward_icu: int = 0,
        ward_er: int = 0,
        ward_ip: int = 0,
    ) -> tuple[list[dict], list[dict]]:
        """
        Score all candidate antibiotics for one patient context.

        Returns:
            top3: top 3 dicts [{antibiotic, probability}, ...]
            all_scores: all 32 antibiotics sorted by probability descending
        """
        if not self.is_available():
            raise RuntimeError(
                "ARMD model is not loaded. "
                "Please run armd_model/train_armd.py to train and save the model."
            )

        base_patient = {
            'culture_description': self._normalize(culture_description),
            'organism': self._normalize(organism),
            'age': float(age),
            'gender': self._normalize(gender),
            'wbc_median': float(wbc) if wbc is not None else np.nan,
            'cr_median': float(cr) if cr is not None else np.nan,
            'lactate_median': float(lactate) if lactate is not None else np.nan,
            'procalcitonin_median': float(procalcitonin) if procalcitonin is not None else np.nan,
            'ward__icu': int(ward_icu),
            'ward__er': int(ward_er),
            'ward__ip': int(ward_ip),
        }

        rows = []
        for ab in self.selected_antibiotics:
            row = {c: 0 for c in self.feature_cols}
            for k, v in base_patient.items():
                if k in row:
                    row[k] = v
            row['antibiotic'] = ab
            rows.append(row)

        score_df = pd.DataFrame(rows)[self.feature_cols]
        probs = self.model.predict_proba(score_df)[:, 1]

        all_scores = sorted(
            [
                {'antibiotic': ab, 'probability': round(float(p), 4)}
                for ab, p in zip(self.selected_antibiotics, probs)
            ],
            key=lambda x: x['probability'],
            reverse=True,
        )

        return all_scores[:3], all_scores

    def get_model_info(self) -> dict:
        categorical_cols = self.metadata.get('categorical_cols', [])
        numeric_cols = self.metadata.get('numeric_cols', [])
        binary_cols = self.metadata.get('binary_cols', [])

        return {
            'model_type': 'RandomForest (ARMD)',
            'n_antibiotics': len(self.selected_antibiotics),
            'n_features': len(self.feature_cols),
            'best_threshold': self.best_threshold,
            'available': self.is_available(),
            'antibiotics': self.selected_antibiotics,
            'feature_groups': {
                'categorical': categorical_cols,
                'numeric': numeric_cols,
                'binary': binary_cols,
            },
            'test_summary': self.test_summary,
            'top_feature_importances': self.feature_importances,
            'artifacts': {
                'recommendation_model': 'rf_top3_recommender_optimized.joblib',
                'feature_columns': 'feature_cols.joblib',
                'selected_antibiotics': 'selected_antibiotics.joblib',
                'best_threshold': 'best_threshold.joblib',
                'test_summary': 'split_test_summary.joblib',
                'feature_importances': 'feature_importances.joblib',
            },
            'metadata': self.metadata,
        }
