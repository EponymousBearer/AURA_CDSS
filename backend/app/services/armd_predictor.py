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
        self.model_is_calibrated: bool = False
        self.feature_cols: list[str] = []
        self.selected_antibiotics: list[str] = SELECTED_ANTIBIOTICS
        self.best_threshold: float = 0.5
        self.metadata: dict = {}
        self.test_summary: list[dict] = []
        self.feature_importances: list[dict] = []
        self.organism_panel: dict = {}  # organism -> clinically-tested antibiotics (antibiogram)
        # Prior-history feature index (M3/T3.2): normalized token -> model column.
        # Built from feature_cols so the accepted vocabulary always tracks the artifact.
        self._prior_index: dict[str, dict[str, str]] = {'abxclass': {}, 'org': {}}
        # Per-prediction TreeSHAP explanations (M3/T3.1). Lazy + best-effort: the
        # explainer and shap import are built on first use and any failure degrades
        # gracefully (recommendations still returned, explanation omitted).
        self._explain_pipeline = None          # raw sklearn Pipeline used for SHAP
        self._explainer = None                 # cached shap.TreeExplainer
        self._explain_disabled = False         # set True once if shap is unusable
        self._name_groups: list | None = None  # transformed-col -> (group_key, label)
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
            # Prefer the calibrated model (M1/T1.3): isotonic calibration is
            # monotonic, so rankings/Top-3 are identical to the base RF, but the
            # returned probabilities are decision-grade (Brier 0.168 -> 0.099).
            # Fall back to the raw RF if the calibrated artifact isn't present.
            calibrated_path = artifacts_dir / 'rf_top3_recommender_calibrated.joblib'
            base_path = artifacts_dir / 'rf_top3_recommender_optimized.joblib'
            if calibrated_path.exists():
                self.model = joblib.load(calibrated_path)
                self.model_is_calibrated = True
                logger.info("Loaded CALIBRATED recommender (isotonic).")
            else:
                self.model = joblib.load(base_path)
                self.model_is_calibrated = False
                logger.info("Calibrated artifact not found; loaded raw RF recommender.")
            self.feature_cols = joblib.load(artifacts_dir / 'feature_cols.joblib')
            self._build_prior_index()
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

            panel_path = artifacts_dir / 'organism_antibiotic_panel.json'
            if panel_path.exists():
                with open(panel_path) as f:
                    self.organism_panel = json.load(f).get('panel', {})
                logger.info(f"Antibiogram panel loaded for {len(self.organism_panel)} organisms")

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

    @staticmethod
    def _norm_token(value: str) -> str:
        """Canonicalize a prior-history token to match a column suffix
        (lowercase, spaces/hyphens -> underscore)."""
        return str(value).strip().lower().replace(' ', '_').replace('-', '_')

    def _build_prior_index(self):
        """Map normalized suffix -> full model column for the prior-history features,
        so the accepted vocabulary is derived from the artifact, not hardcoded."""
        self._prior_index = {'abxclass': {}, 'org': {}}
        for col in self.feature_cols:
            if col.startswith('prior_abxclass__'):
                self._prior_index['abxclass'][col[len('prior_abxclass__'):]] = col
            elif col.startswith('prior_org__'):
                self._prior_index['org'][col[len('prior_org__'):]] = col

    def _build_prior_flags(
        self,
        prior_abx_classes: Optional[list[str]],
        prior_organisms: Optional[list[str]],
    ) -> dict[str, int]:
        """Turn the supplied prior-history selections into 1-flags on the matching
        model columns. Unknown tokens are ignored (additive / robust — never errors)."""
        flags: dict[str, int] = {}
        for token in (prior_abx_classes or []):
            col = self._prior_index['abxclass'].get(self._norm_token(token))
            if col:
                flags[col] = 1
        for token in (prior_organisms or []):
            col = self._prior_index['org'].get(self._norm_token(token))
            if col:
                flags[col] = 1
        return flags

    # Nicer display labels for the option vocabulary (fallback: title-case the suffix).
    _PRIOR_LABELS = {
        'beta_lactam': 'Beta-lactam',
        'macrolide_lincosamide': 'Macrolide / lincosamide',
        'polymyxin,_lipopeptide': 'Polymyxin / lipopeptide',
        'folate_synthesis_inhibitor': 'Folate-synthesis inhibitor',
        'combination_antibiotic': 'Combination antibiotic',
        'urinary_antiseptic': 'Urinary antiseptic',
        'cons': 'CoNS (coag-negative staph)',
    }

    def _prior_label(self, suffix: str) -> str:
        if suffix in self._PRIOR_LABELS:
            return self._PRIOR_LABELS[suffix]
        return suffix.replace('_', ' ').replace(',', '').strip().capitalize()

    def get_prior_history_options(self) -> dict:
        """Selectable prior-history vocabulary for the UI (value = model suffix)."""
        return {
            'antibiotic_classes': [
                {'value': s, 'label': self._prior_label(s)}
                for s in sorted(self._prior_index['abxclass'])
            ],
            'organisms': [
                {'value': s, 'label': self._prior_label(s)}
                for s in sorted(self._prior_index['org'])
            ],
        }

    # ── Per-prediction TreeSHAP explanations (M3/T3.1) ───────────────────────
    # Human labels + grouping for the transformed one-hot columns, so an
    # explanation reads as clinical factors (Organism, Prior antibiotic exposure)
    # rather than raw one-hot column names.
    _EXPLAIN_LABELS = {
        'antibiotic': 'Drug identity',
        'organism': 'Organism',
        'culture_description': 'Culture site',
        'age': 'Age',
        'gender': 'Sex',
        'wbc_median': 'WBC',
        'cr_median': 'Creatinine',
        'lactate_median': 'Lactate',
        'procalcitonin_median': 'Procalcitonin',
    }

    def _orig_feature_of(self, transformed_name: str) -> Optional[str]:
        """Map a preprocessor output column (e.g. 'cat__organism_escherichia coli',
        'num__ward__icu') back to its original model feature column."""
        core = transformed_name.split('__', 1)[1] if transformed_name.startswith(('cat__', 'num__')) else transformed_name
        if core in self.feature_cols:
            return core
        cands = [c for c in self.feature_cols if core.startswith(c + '_')]
        return max(cands, key=len) if cands else None

    def _explain_group(self, orig: Optional[str]) -> Optional[tuple]:
        """(group_key, display_label) for an original feature, bucketing the many
        prior_*/ward_* flags into single interpretable factors."""
        if orig is None:
            return None
        if orig.startswith('prior_abxclass__'):
            return ('prior_antibiotic_exposure', 'Prior antibiotic exposure')
        if orig.startswith('prior_org__'):
            return ('prior_organisms', 'Prior organisms')
        if orig.startswith('ward__'):
            return ('ward', 'Ward')
        return (orig, self._EXPLAIN_LABELS.get(orig, orig))

    def _resolve_explain_pipeline(self):
        """The raw sklearn Pipeline (prep + rf) to run SHAP on — reused from the
        already-loaded model (no second load), so startup RAM is unchanged. Isotonic
        calibration is monotonic, so explaining the underlying RF is valid."""
        m = self.model
        if hasattr(m, 'steps'):                       # raw pipeline already
            return m
        est = getattr(m, 'estimator', None)           # CalibratedClassifierCV(cv='prefit')
        if hasattr(est, 'steps'):
            return est
        ccs = getattr(m, 'calibrated_classifiers_', None)
        if ccs:
            for attr in ('estimator', 'base_estimator'):
                e = getattr(ccs[0], attr, None)
                if hasattr(e, 'steps'):
                    return e
        return None

    @staticmethod
    def _explanations_enabled() -> bool:
        """Whether to compute TreeSHAP. Default: ON in dev/demo, OFF in production —
        shap/numba can OOM a 512 MB host on first import (an uncatchable SIGKILL), so
        it's opt-in live via ENABLE_SHAP=1. ENABLE_SHAP overrides in either direction."""
        flag = os.getenv('ENABLE_SHAP')
        if flag is not None:
            return flag.strip().lower() in ('1', 'true', 'yes', 'on')
        return os.getenv('ENVIRONMENT', 'development').strip().lower() != 'production'

    def _ensure_explainer(self):
        """Lazily build the shap.TreeExplainer + column->group map. Best-effort:
        on any failure, disable explanations permanently (recommendations unaffected)."""
        if self._explain_disabled or not self._explanations_enabled():
            return None
        if self._explainer is not None:
            return self._explainer
        if self._explain_pipeline is None:
            self._explain_pipeline = self._resolve_explain_pipeline()
        if self._explain_pipeline is None:
            self._explain_disabled = True
            return None
        try:
            import shap  # heavy, optional — imported only when an explanation is requested
            pre = self._explain_pipeline.steps[0][1]
            rf = self._explain_pipeline.steps[1][1]
            names = list(pre.get_feature_names_out())
            self._name_groups = [self._explain_group(self._orig_feature_of(n)) for n in names]
            self._explainer = shap.TreeExplainer(rf)
            logger.info("TreeSHAP explainer ready (%d transformed features).", len(names))
            return self._explainer
        except Exception as exc:
            logger.warning("SHAP unavailable; explanations disabled: %s", exc)
            self._explain_disabled = True
            return None

    def _explain_rows(self, base_patient: dict, antibiotics: list[str], top_k: int = 4) -> Optional[list]:
        """Top contributing clinical factors (signed) per antibiotic, via TreeSHAP.
        Returns None if explanations are unavailable — never raises to the caller."""
        explainer = self._ensure_explainer()
        if explainer is None:
            return None
        try:
            rows = []
            for ab in antibiotics:
                row = {c: 0 for c in self.feature_cols}
                for k, v in base_patient.items():
                    if k in row:
                        row[k] = v
                row['antibiotic'] = ab
                rows.append(row)
            X = pd.DataFrame(rows)[self.feature_cols]
            Xt = self._explain_pipeline.steps[0][1].transform(X)
            sv = explainer.shap_values(Xt)
            # Normalise to the P(susceptible=1) contribution matrix (n_rows, n_features).
            if isinstance(sv, list):
                s1 = sv[1]
            elif getattr(sv, 'ndim', 2) == 3:
                s1 = sv[:, :, 1]
            else:
                s1 = sv

            out = []
            for i in range(len(antibiotics)):
                agg: dict = {}
                for j, grp in enumerate(self._name_groups):
                    if grp is None:
                        continue
                    agg[grp] = agg.get(grp, 0.0) + float(s1[i, j])
                top = sorted(agg.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
                out.append([
                    {
                        'feature': gkey,
                        'label': glabel,
                        'contribution': round(contrib, 4),
                        'direction': 'increases' if contrib >= 0 else 'decreases',
                    }
                    for (gkey, glabel), contrib in top
                ])
            return out
        except Exception as exc:
            logger.warning("SHAP explanation failed for this request: %s", exc)
            return None

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
        prior_abx_classes: Optional[list[str]] = None,
        prior_organisms: Optional[list[str]] = None,
        explain: bool = False,
    ) -> tuple[list[dict], list[dict]]:
        """
        Score all candidate antibiotics for one patient context.

        prior_abx_classes / prior_organisms (M3/T3.2): the patient's prior antibiotic-
        class exposure and prior infecting organisms. Previously these features were
        always zero at inference; now supplied selections set the matching
        prior_abxclass__*/prior_org__* columns to 1 so patient history influences the score.

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
        # M3/T3.2: activate prior-history features (no longer zero-filled below).
        base_patient.update(self._build_prior_flags(prior_abx_classes, prior_organisms))

        # Layer 2 (clinical filter): restrict candidates to antibiotics the lab
        # actually tests for this organism (data-derived antibiogram). Drugs never
        # tested for the organism (e.g. metronidazole vs E. coli, ertapenem vs
        # Pseudomonas) are excluded so they can't dominate the ranking. Unknown
        # organisms fall back to the full panel rather than returning nothing.
        org_norm = self._normalize(organism)
        allowed = self.organism_panel.get(org_norm)
        candidates = [ab for ab in self.selected_antibiotics if ab in allowed] if allowed else []
        if not candidates:
            candidates = list(self.selected_antibiotics)

        rows = []
        for ab in candidates:
            row = {c: 0 for c in self.feature_cols}
            for k, v in base_patient.items():
                if k in row:
                    row[k] = v
            row['antibiotic'] = ab
            rows.append(row)

        score_df = pd.DataFrame(rows)[self.feature_cols]
        probs = self.model.predict_proba(score_df)[:, 1]

        # Layer 3 (ranking): rank the allowed candidates by absolute P(susceptible).
        all_scores = sorted(
            [
                {'antibiotic': ab, 'probability': round(float(p), 4)}
                for ab, p in zip(candidates, probs)
            ],
            key=lambda x: x['probability'],
            reverse=True,
        )

        top3 = [dict(d) for d in all_scores[:3]]  # copies so explanations don't leak into all_predictions
        # M3/T3.1: attach per-drug TreeSHAP explanations for the top 3 (best-effort).
        if explain and top3:
            explanations = self._explain_rows(base_patient, [d['antibiotic'] for d in top3])
            if explanations:
                for item, factors in zip(top3, explanations):
                    item['explanation'] = factors

        return top3, all_scores

    def get_model_info(self) -> dict:
        categorical_cols = self.metadata.get('categorical_cols', [])
        numeric_cols = self.metadata.get('numeric_cols', [])
        binary_cols = self.metadata.get('binary_cols', [])

        return {
            'model_type': 'RandomForest (ARMD)',
            'calibrated': self.model_is_calibrated,
            'calibration_method': 'isotonic' if self.model_is_calibrated else None,
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
            'prior_history_options': self.get_prior_history_options(),
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
