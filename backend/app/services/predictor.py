"""
ML Prediction service using trained CatBoost models.
"""

import os
import pickle
import json
import logging
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from catboost import Pool

from app.utils.logger import get_logger

logger = get_logger(__name__)

ORGANISM_NORMALIZATION = {
    "ESCHERICHIA COLI": "E. coli",
    "KLEBSIELLA PNEUMONIAE": "K. pneumoniae",
    "PSEUDOMONAS AERUGINOSA": "P. aeruginosa",
    "ACINETOBACTER BAUMANNII": "A. baumannii",
    "STAPHYLOCOCCUS AUREUS": "S. aureus",
    "ENTEROCOCCUS FAECIUM": "E. faecium",
    "STREPTOCOCCUS PNEUMONIAE": "S. pneumoniae",
    "COAG NEGATIVE STAPHYLOCOCCUS": "COAG NEGATIVE STAPHYLOCOCCUS",
    "ENTEROCOCCUS FAECALIS": "ENTEROCOCCUS FAECALIS",
    "KLEBSIELLA OXYTOCA": "KLEBSIELLA OXYTOCA",
    "PROTEUS MIRABILIS": "PROTEUS MIRABILIS",
    "STAPHYLOCOCCUS EPIDERMIDIS": "STAPHYLOCOCCUS EPIDERMIDIS",
}


class PredictionService:
    """
    Service for antibiotic susceptibility predictions.
    Loads trained CatBoost models and makes predictions.
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize prediction service.

        Args:
            model_path: Path to the saved model file
        """
        self.models: Dict[str, Any] = {}
        self.antibiotic_list: List[str] = []
        self.categorical_features: List[str] = []
        self.positive_rates: Dict[str, float] = {}
        self.model_metadata: Dict[str, Any] = {}

        # Set default model path
        if model_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            model_path = os.path.join(base_dir, "model", "antibiotic_model.pkl")

        self.model_path = model_path
        self.metadata_path = os.path.join(os.path.dirname(self.model_path), "model_metadata.json")
        self._load_models()
        self._load_metadata()

    def _load_models(self) -> None:
        """
        Load trained models from pickle file.
        """
        try:
            if not os.path.exists(self.model_path):
                logger.warning(f"Model file not found at {self.model_path}")
                # Use fallback predictions
                self._init_fallback()
                return

            logger.info(f"Loading models from {self.model_path}")

            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)

            self.models = model_data.get('models', {})
            self.antibiotic_list = model_data.get('antibiotic_list', [])
            self.categorical_features = model_data.get('categorical_features', [])
            self.positive_rates = model_data.get('positive_rates', {})

            logger.info(f"Loaded {len(self.models)} antibiotic models")
            logger.info(f"Available antibiotics: {len(self.antibiotic_list)}")

        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")
            self._init_fallback()

    def _load_metadata(self) -> None:
        """Load trained model metadata from JSON if available."""
        try:
            if not os.path.exists(self.metadata_path):
                logger.warning(f"Metadata file not found at {self.metadata_path}")
                self.model_metadata = {
                    "trained_at": None,
                    "n_antibiotics": len(self.antibiotic_list),
                    "training_samples": 0,
                    "antibiotics": [],
                }
                return

            with open(self.metadata_path, "r") as f:
                self.model_metadata = json.load(f)

            logger.info("Loaded model metadata from %s", self.metadata_path)
        except Exception as e:
            logger.error(f"Error loading metadata: {str(e)}")
            self.model_metadata = {
                "trained_at": None,
                "n_antibiotics": len(self.antibiotic_list),
                "training_samples": 0,
                "antibiotics": [],
            }

    def _init_fallback(self) -> None:
        """
        Initialize fallback mode with simplified prediction logic.
        Used when models are not available.
        """
        logger.warning("Using fallback prediction mode")
        self.antibiotic_list = [
            'Ceftriaxone', 'Ciprofloxacin', 'Meropenem',
            'Piperacillin-Tazobactam', 'Vancomycin', 'Linezolid'
        ]
        self.categorical_features = ['organism', 'gender', 'kidney_function', 'severity']

    def _get_fallback_probability(self, organism: str, antibiotic: str) -> float:
        """
        Get fallback probability based on organism-antibiotic pairing.
        """
        # Simplified resistance patterns
        resistance_patterns = {
            'E. coli': {'Ceftriaxone': 0.85, 'Ciprofloxacin': 0.70, 'Meropenem': 0.98},
            'K. pneumoniae': {'Ceftriaxone': 0.75, 'Ciprofloxacin': 0.80, 'Meropenem': 0.95},
            'P. aeruginosa': {'Meropenem': 0.85, 'Piperacillin-Tazobactam': 0.80},
            'S. aureus': {'Vancomycin': 0.95, 'Linezolid': 0.98},
            'E. faecium': {'Vancomycin': 0.70, 'Linezolid': 0.95},
            'S. pneumoniae': {'Ceftriaxone': 0.95, 'Ciprofloxacin': 0.85},
            'Enterococcus spp': {'Vancomycin': 0.85, 'Linezolid': 0.95},
            'A. baumannii': {'Meropenem': 0.60, 'Ciprofloxacin': 0.40}
        }

        default_prob = 0.70
        organism_probs = resistance_patterns.get(organism, {})
        return organism_probs.get(antibiotic, default_prob)

    def _organism_compatibility(self, organism: str, antibiotic: str) -> float:
        """
        Return an organism-antibiotic compatibility weight.

        This acts as a clinical plausibility prior for ranking and prevents
        globally high-probability classes from dominating all organisms.
        """
        recommended_map = {
            'E. coli': {
                'Nitrofurantoin', 'Ceftriaxone', 'Ciprofloxacin', 'Gentamicin',
                'Amikacin', 'Piperacillin-Tazobactam', 'Meropenem', 'Ertapenem'
            },
            'K. pneumoniae': {
                'Ceftriaxone', 'Cefepime', 'Ceftazidime', 'Ciprofloxacin',
                'Gentamicin', 'Amikacin', 'Piperacillin-Tazobactam', 'Meropenem',
                'Imipenem', 'Ertapenem'
            },
            'P. aeruginosa': {
                'Piperacillin-Tazobactam', 'Ceftazidime', 'Cefepime',
                'Meropenem', 'Imipenem', 'Ciprofloxacin', 'Levofloxacin',
                'Gentamicin', 'Tobramycin', 'Amikacin'
            },
            'A. baumannii': {
                'Meropenem', 'Imipenem', 'Amikacin', 'Tigecycline',
                'Minocycline', 'Colistin'
            },
            'S. aureus': {
                'Cefazolin', 'Vancomycin', 'Linezolid', 'Daptomycin',
                'Clindamycin', 'Trimethoprim-Sulfamethoxazole'
            },
            'E. faecium': {
                'Ampicillin', 'Vancomycin', 'Linezolid', 'Daptomycin'
            },
            'S. pneumoniae': {
                'Amoxicillin', 'Ceftriaxone', 'Levofloxacin',
                'Vancomycin', 'Linezolid'
            },
            'Enterococcus spp': {
                'Ampicillin', 'Amoxicillin', 'Vancomycin', 'Linezolid', 'Daptomycin'
            }
        }

        supported = recommended_map.get(organism)
        if not supported:
            return 1.0

        if antibiotic in supported:
            return 1.0

        # Keep unsupported agents possible but heavily deprioritized.
        return 0.25

    def rank_antibiotics(self,
                         predictions: Dict[str, float],
                         organism: str,
                         top_k: int = 3) -> List[tuple[str, float]]:
        """
        Rank antibiotics using adjusted score, then return original probabilities.

        Raw one-vs-rest probabilities are not directly comparable across labels.
        We adjust by baseline positive rates and organism compatibility.
        """
        ranked = []
        for antibiotic, prob in predictions.items():
            base_rate = float(self.positive_rates.get(antibiotic, 0.5))
            compatibility = self._organism_compatibility(organism, antibiotic)

            # Baseline correction: penalize labels that are globally positive often.
            score = (prob - 0.5 * base_rate) * compatibility
            ranked.append((antibiotic, prob, score))

        ranked.sort(key=lambda x: x[2], reverse=True)
        return [(antibiotic, prob) for antibiotic, prob, _ in ranked[:top_k]]

    def predict(self,
                organism: str,
                age: int,
                gender: str,
                kidney_function: str,
                severity: str) -> Dict[str, float]:
        """
        Predict susceptibility for all antibiotics.

        Args:
            organism: Bacterial organism name
            age: Patient age
            gender: Patient gender (M/F)
            kidney_function: Kidney function status (normal/low)
            severity: Infection severity (low/medium/high)

        Returns:
            Dictionary mapping antibiotic names to probability scores
        """
        organism = self._normalize_organism(organism)
        logger.info(f"Making prediction for organism: {organism}")

        # Create feature DataFrame
        features = self._build_feature_frame(
            organism=organism,
            age=age,
            gender=gender,
            kidney_function=kidney_function,
            severity=severity,
        )

        predictions = {}

        for antibiotic in self.antibiotic_list:
            model = self.models.get(antibiotic)

            if model is not None:
                # Use trained model
                try:
                    prob = model.predict_proba(features)[0][1]
                    predictions[antibiotic] = float(prob)
                except Exception as e:
                    logger.warning(f"Model prediction failed for {antibiotic}: {str(e)}")
                    predictions[antibiotic] = self._get_fallback_probability(organism, antibiotic)
            else:
                # Use fallback
                predictions[antibiotic] = self._get_fallback_probability(organism, antibiotic)

        return predictions

    def _normalize_organism(self, organism: str) -> str:
        return ORGANISM_NORMALIZATION.get(
            str(organism).strip().upper(),
            str(organism).strip(),
        )

    def _build_feature_frame(
        self,
        organism: str,
        age: int,
        gender: str,
        kidney_function: str,
        severity: str,
    ) -> pd.DataFrame:
        return pd.DataFrame([{
            'organism': organism,
            'age': age,
            'gender': gender,
            'kidney_function': kidney_function,
            'severity': severity,
        }])

    def get_feature_importance_for_prediction(
        self,
        organism: str,
        age: int,
        gender: str,
        kidney_function: str,
        severity: str,
        antibiotic: str,
    ) -> Dict[str, float]:
        """
        Return SHAP-based feature importance for one antibiotic prediction.

        The values are normalized to percentages so they sum to 100.
        """
        organism = self._normalize_organism(organism)
        model = self.models.get(antibiotic)

        if model is None:
            raise ValueError(f"No trained model available for antibiotic: {antibiotic}")

        features = self._build_feature_frame(
            organism=organism,
            age=age,
            gender=gender,
            kidney_function=kidney_function,
            severity=severity,
        )

        categorical_columns = [
            column for column in self.categorical_features
            if column in features.columns
        ]
        pool = Pool(features, cat_features=categorical_columns)

        shap_values = model.get_feature_importance(pool, type='ShapValues')
        shap_array = np.asarray(shap_values)

        if shap_array.ndim != 2 or shap_array.shape[0] == 0:
            raise ValueError("Unexpected SHAP output returned by the model")

        feature_values = shap_array[0][: len(features.columns)]
        absolute_values = np.abs(feature_values)
        total = float(np.sum(absolute_values))

        if total == 0:
            equal_share = 100.0 / len(features.columns)
            return {column: equal_share for column in features.columns}

        percentages = (absolute_values / total) * 100.0

        return {
            column: float(percentages[index])
            for index, column in enumerate(features.columns)
        }

    def get_available_antibiotics(self) -> List[Dict[str, Any]]:
        """
        Get list of available antibiotics with metadata.

        Returns:
            List of antibiotic information dictionaries
        """
        return [
            {
                "name": abx,
                "model_loaded": abx in self.models and self.models[abx] is not None
            }
            for abx in self.antibiotic_list
        ]

    def get_model_info(self) -> Dict[str, Any]:
        """Return model inventory and quality metadata."""
        antibiotics = self.model_metadata.get("antibiotics", [])
        loaded_count = sum(1 for antibiotic in self.antibiotic_list if self.models.get(antibiotic) is not None)

        return {
            "total_models_loaded": loaded_count,
            "model_trained_at": self.model_metadata.get("trained_at"),
            "training_samples": self.model_metadata.get("training_samples", 0),
            "n_antibiotics": self.model_metadata.get("n_antibiotics", len(self.antibiotic_list)),
            "antibiotics": [
                {
                    "name": item.get("name"),
                    "auc": float(item.get("auc", 0.0)),
                    "f1": float(item.get("f1", 0.0)),
                    "accuracy": float(item.get("accuracy", 0.0)),
                    "status": item.get("status", "included"),
                }
                for item in antibiotics
            ],
        }
