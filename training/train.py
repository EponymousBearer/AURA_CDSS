"""
Training module for antibiotic susceptibility prediction using CatBoost.
Trains separate binary classifiers for each antibiotic.
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import pandas as pd
import numpy as np
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
import json
from datetime import datetime, timezone

from preprocess import DataPreprocessor, preprocess_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TRAINING_DIR = Path(__file__).resolve().parent


class AntibioticPredictorTrainer:
    """
    Trainer class for antibiotic susceptibility prediction.
    Trains individual CatBoost models for each antibiotic.
    """

    def __init__(self, categorical_features: List[str], output_dir: str = "./output"):
        self.categorical_features = categorical_features
        self.output_dir = output_dir
        self.models: Dict[str, CatBoostClassifier] = {}
        self.metrics: Dict[str, Dict] = {}
        self.model_status: Dict[str, str] = {}
        self.antibiotic_list: List[str] = []
        self.positive_rates: Dict[str, float] = {}

        os.makedirs(output_dir, exist_ok=True)

    def train_single_model(self, X_train: pd.DataFrame, y_train: pd.Series,
                          X_val: pd.DataFrame, y_val: pd.Series,
                          antibiotic: str) -> CatBoostClassifier:
        """
        Train a single CatBoost model for one antibiotic.

        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features
            y_val: Validation labels
            antibiotic: Antibiotic name

        Returns:
            Trained CatBoostClassifier
        """
        logger.info(f"Training model for {antibiotic}")

        model = self._create_model(y_train)
        if model is None:
            return None

        model.fit(
            X_train, y_train,
            eval_set=(X_val, y_val),
            verbose=False
        )

        return model

    def _create_model(self, y_train: pd.Series) -> Optional[CatBoostClassifier]:
        """Create a CatBoost model with class weights based on the training labels."""
        class_counts = y_train.value_counts()
        if len(class_counts) < 2:
            logger.warning("Only one class present, skipping model creation")
            return None

        total = len(y_train)
        class_weights = {
            0: total / (2 * class_counts.get(0, 1)),
            1: total / (2 * class_counts.get(1, 1)),
        }

        return CatBoostClassifier(
            iterations=500,
            depth=6,
            learning_rate=0.1,
            loss_function='Logloss',
            eval_metric='AUC',
            random_seed=42,
            early_stopping_rounds=50,
            verbose=False,
            class_weights=class_weights,
            cat_features=self.categorical_features
        )

    def _cross_validate_auc(self, X: pd.DataFrame, y: pd.Series, antibiotic: str) -> Tuple[float, float]:
        """Run 5-fold cross validation and return mean/std of validation AUC."""
        class_counts = y.value_counts()
        if len(class_counts) < 2 or class_counts.min() < 5:
            logger.warning(
                "Insufficient class counts for 5-fold CV on %s; returning zero CV metrics",
                antibiotic,
            )
            return 0.0, 0.0

        splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        auc_scores: List[float] = []

        for fold_index, (train_index, val_index) in enumerate(splitter.split(X, y), start=1):
            X_fold_train = X.iloc[train_index]
            y_fold_train = y.iloc[train_index]
            X_fold_val = X.iloc[val_index]
            y_fold_val = y.iloc[val_index]

            if len(np.unique(y_fold_train)) < 2 or len(np.unique(y_fold_val)) < 2:
                logger.warning("Skipping fold %s for %s due to single-class split", fold_index, antibiotic)
                continue

            model = self._create_model(y_fold_train)
            if model is None:
                continue

            model.fit(X_fold_train, y_fold_train, eval_set=(X_fold_val, y_fold_val), verbose=False)
            probabilities = model.predict_proba(X_fold_val)[:, 1]
            auc_scores.append(roc_auc_score(y_fold_val, probabilities))

        if not auc_scores:
            return 0.0, 0.0

        return float(np.mean(auc_scores)), float(np.std(auc_scores, ddof=0))

    def evaluate_model(self, model: CatBoostClassifier,
                      X_val: pd.DataFrame, y_val: pd.Series,
                      antibiotic: str) -> Dict[str, float]:
        """
        Evaluate model performance.

        Args:
            model: Trained model
            X_val: Validation features
            y_val: Validation labels
            antibiotic: Antibiotic name

        Returns:
            Dictionary of metrics
        """
        if model is None:
            return {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0,
                   'f1': 0.0, 'auc': 0.0}

        predictions = model.predict(X_val)
        probabilities = model.predict_proba(X_val)[:, 1]

        metrics = {
            'accuracy': accuracy_score(y_val, predictions),
            'precision': precision_score(y_val, predictions, zero_division=0),
            'recall': recall_score(y_val, predictions, zero_division=0),
            'f1': f1_score(y_val, predictions, zero_division=0),
            'auc': roc_auc_score(y_val, probabilities) if len(np.unique(y_val)) > 1 else 0.5
        }

        logger.info(f"{antibiotic} metrics: {metrics}")
        return metrics

    def train_all_models(self, X_train: pd.DataFrame, y_train: pd.DataFrame,
                        X_val: pd.DataFrame, y_val: pd.DataFrame,
                        antibiotic_columns: List[str]) -> None:
        """
        Train models for all antibiotics.

        Args:
            X_train: Training features
            y_train: Training targets (multi-column)
            X_val: Validation features
            y_val: Validation targets (multi-column)
            antibiotic_columns: List of antibiotic column names
        """
        self.antibiotic_list = antibiotic_columns

        for antibiotic in antibiotic_columns:
            logger.info(f"\n--- Training for {antibiotic} ---")

            # Baseline prevalence of susceptibility in training set.
            self.positive_rates[antibiotic] = float(y_train[antibiotic].mean())

            class_counts = y_train[antibiotic].value_counts()
            if len(class_counts) < 2:
                logger.warning(f"Only one class present for {antibiotic}, excluding from final model set")
                self.models[antibiotic] = None
                self.metrics[antibiotic] = self.evaluate_model(None, X_val, y_val[antibiotic], antibiotic)
                self.metrics[antibiotic]["cv_auc_mean"] = 0.0
                self.metrics[antibiotic]["cv_auc_std"] = 0.0
                self.model_status[antibiotic] = "excluded_single_class"
                continue

            cv_auc_mean, cv_auc_std = self._cross_validate_auc(X_train, y_train[antibiotic], antibiotic)

            model = self.train_single_model(
                X_train, y_train[antibiotic],
                X_val, y_val[antibiotic],
                antibiotic
            )

            self.models[antibiotic] = model

            metrics = self.evaluate_model(
                model, X_val, y_val[antibiotic],
                antibiotic
            )
            metrics["cv_auc_mean"] = cv_auc_mean
            metrics["cv_auc_std"] = cv_auc_std
            self.metrics[antibiotic] = metrics

            if metrics.get("auc", 0.0) < 0.55:
                self.model_status[antibiotic] = "excluded_low_auc"
            else:
                self.model_status[antibiotic] = "included"

        removed_antibiotics = [
            antibiotic for antibiotic, status in self.model_status.items()
            if status != "included"
        ]

        if removed_antibiotics:
            logger.info("Excluding low-quality antibiotics: %s", ", ".join(removed_antibiotics))

        included_antibiotics = [
            antibiotic for antibiotic in self.antibiotic_list
            if self.model_status.get(antibiotic) == "included"
        ]

        self.models = {antibiotic: self.models[antibiotic] for antibiotic in included_antibiotics}
        self.metrics = {antibiotic: self.metrics[antibiotic] for antibiotic in self.antibiotic_list}
        self.positive_rates = {antibiotic: self.positive_rates[antibiotic] for antibiotic in included_antibiotics}
        self.antibiotic_list = included_antibiotics

    def _build_metadata(self, training_samples: int) -> Dict[str, Any]:
        """Build metadata payload for downstream model loading and inspection."""
        trained_at = datetime.now(timezone.utc).isoformat()
        return {
            "trained_at": trained_at,
            "n_antibiotics": len(self.antibiotic_list),
            "training_samples": int(training_samples),
            "antibiotics": [
                {
                    "name": antibiotic,
                    "auc": float(self.metrics.get(antibiotic, {}).get("auc", 0.0)),
                    "f1": float(self.metrics.get(antibiotic, {}).get("f1", 0.0)),
                    "accuracy": float(self.metrics.get(antibiotic, {}).get("accuracy", 0.0)),
                    "cv_auc_mean": float(self.metrics.get(antibiotic, {}).get("cv_auc_mean", 0.0)),
                    "cv_auc_std": float(self.metrics.get(antibiotic, {}).get("cv_auc_std", 0.0)),
                    "status": self.model_status.get(antibiotic, "excluded_low_auc"),
                }
                for antibiotic in self.metrics.keys()
            ],
        }

    def save_models(self, model_filename: str = "antibiotic_model.pkl") -> str:
        """
        Save all trained models and metadata to a pickle file.

        Args:
            model_filename: Name of the output file

        Returns:
            Path to saved model file
        """
        model_data = {
            'models': self.models,
            'metrics': self.metrics,
            'antibiotic_list': self.antibiotic_list,
            'categorical_features': self.categorical_features,
            'positive_rates': self.positive_rates,
            'model_status': self.model_status,
        }

        model_path = os.path.join(self.output_dir, model_filename)
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"Saved models to {model_path}")

        # Also save metrics as JSON for easy viewing
        metrics_path = os.path.join(self.output_dir, "metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        quality_report_path = os.path.join(self.output_dir, "model_quality_report.json")
        with open(quality_report_path, 'w') as f:
            json.dump(
                [
                    {
                        "name": antibiotic,
                        "auc": float(self.metrics.get(antibiotic, {}).get("auc", 0.0)),
                        "f1": float(self.metrics.get(antibiotic, {}).get("f1", 0.0)),
                        "accuracy": float(self.metrics.get(antibiotic, {}).get("accuracy", 0.0)),
                        "status": self.model_status.get(antibiotic, "excluded_low_auc"),
                    }
                    for antibiotic in self.metrics.keys()
                ],
                f,
                indent=2,
            )

        return model_path

    def get_feature_importance(self, antibiotic: str) -> Dict[str, float]:
        """
        Get feature importance for a specific antibiotic model.

        Args:
            antibiotic: Antibiotic name

        Returns:
            Dictionary of feature names to importance scores
        """
        if antibiotic not in self.models or self.models[antibiotic] is None:
            return {}

        model = self.models[antibiotic]
        importance = model.get_feature_importance()
        feature_names = model.feature_names_

        return dict(sorted(zip(feature_names, importance),
                          key=lambda x: x[1], reverse=True))


def train_pipeline(data_dir: str = "./data",
                  output_dir: str = "./output",
                  model_path: str = "../backend/model") -> str:
    """
    Complete training pipeline.

    Args:
        data_dir: Directory containing processed data
        output_dir: Directory to save training outputs
        model_path: Directory to copy final model

    Returns:
        Path to saved model file
    """
    logger.info("=" * 60)

    data_dir_path = Path(data_dir)
    if not data_dir_path.is_absolute():
        data_dir_path = (TRAINING_DIR / data_dir_path).resolve()

    output_dir_path = Path(output_dir)
    if not output_dir_path.is_absolute():
        output_dir_path = (TRAINING_DIR / output_dir_path).resolve()

    model_dir_path = Path(model_path)
    if not model_dir_path.is_absolute():
        model_dir_path = (TRAINING_DIR / model_dir_path).resolve()
    logger.info("Starting Antibiotic Prediction Model Training")
    logger.info("=" * 60)

    # Run preprocessing
    train_path, val_path, test_path, feature_info = preprocess_pipeline(str(data_dir_path))

    # Load processed data
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)

    patient_features = ['organism', 'age', 'gender', 'kidney_function', 'severity']

    X_train = train_df[patient_features]
    y_train = train_df[feature_info['antibiotic_columns']]

    X_val = val_df[patient_features]
    y_val = val_df[feature_info['antibiotic_columns']]

    # Train models
    trainer = AntibioticPredictorTrainer(
        categorical_features=feature_info['categorical_features'],
        output_dir=str(output_dir_path)
    )

    trainer.train_all_models(
        X_train, y_train,
        X_val, y_val,
        feature_info['antibiotic_columns']
    )

    # Save models
    saved_path = trainer.save_models()

    metadata = trainer._build_metadata(training_samples=len(X_train))

    metadata_path = output_dir_path / "model_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    # Copy to backend model directory
    os.makedirs(model_dir_path, exist_ok=True)
    backend_model_path = str(model_dir_path / "antibiotic_model.pkl")
    backend_metadata_path = str(model_dir_path / "model_metadata.json")

    with open(saved_path, 'rb') as src:
        model_data = pickle.load(src)

    with open(backend_model_path, 'wb') as dst:
        pickle.dump(model_data, dst)

    with open(backend_metadata_path, "w") as dst:
        json.dump(metadata, dst, indent=2)

    # Automatically run held-out evaluation for presentation-ready reporting.
    from evaluate import evaluate_model_suite

    evaluate_model_suite(
        data_dir=str(data_dir_path),
        output_dir=str(output_dir_path),
        model_path=saved_path,
        metadata_path=str(metadata_path),
    )

    logger.info(f"Model copied to {backend_model_path}")
    logger.info(f"Metadata copied to {backend_metadata_path}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Training Complete - Summary")
    logger.info("=" * 60)

    avg_metrics = {
        'accuracy': np.mean([m['accuracy'] for m in trainer.metrics.values()]),
        'precision': np.mean([m['precision'] for m in trainer.metrics.values()]),
        'recall': np.mean([m['recall'] for m in trainer.metrics.values()]),
        'f1': np.mean([m['f1'] for m in trainer.metrics.values()]),
        'auc': np.mean([m['auc'] for m in trainer.metrics.values()])
    }

    logger.info(f"Average metrics across all antibiotics:")
    for metric, value in avg_metrics.items():
        logger.info(f"  {metric}: {value:.4f}")

    return backend_model_path


if __name__ == "__main__":
    # Train and save model
    model_path = train_pipeline()
    logger.info(f"\nModel saved to: {model_path}")
