"""Held-out model evaluation script for presentation-ready reporting."""

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, roc_auc_score


TRAINING_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = TRAINING_DIR / "output" / "antibiotic_model.pkl"
DEFAULT_DATA_DIR = TRAINING_DIR / "data"
DEFAULT_METADATA_PATH = TRAINING_DIR / "output" / "model_metadata.json"


def _load_pickle(path: Path) -> Dict[str, Any]:
    with open(path, "rb") as handle:
        return pickle.load(handle)


def _load_metadata(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_auc(y_true: pd.Series, probabilities: np.ndarray) -> Optional[float]:
    if len(np.unique(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, probabilities))


def _format_value(value: Optional[float]) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _format_table(rows: List[Dict[str, Any]]) -> str:
    headers = ["Antibiotic", "Train AUC", "Val AUC", "Test AUC", "Status"]
    widths = [
        max(len(headers[0]), max(len(str(row["name"])) for row in rows)),
        len(headers[1]),
        len(headers[2]),
        len(headers[3]),
        max(len(headers[4]), max(len(str(row["status"])) for row in rows)),
    ]

    def line(columns: List[str]) -> str:
        return " | ".join(text.ljust(widths[index]) for index, text in enumerate(columns))

    separator = "-+-".join("-" * width for width in widths)
    lines = [line(headers), separator]
    for row in rows:
        lines.append(
            line(
                [
                    str(row["name"]),
                    _format_value(row.get("train_auc")),
                    _format_value(row.get("val_auc")),
                    _format_value(row.get("test_auc")),
                    str(row["status"]),
                ]
            )
        )
    return "\n".join(lines)


def _format_confusion_matrix(antibiotic: str, matrix: Dict[str, int]) -> str:
    return (
        f"\n{antibiotic}\n"
        f"              Pred 0 | Pred 1\n"
        f"Actual 0      {matrix['tn']:>6} | {matrix['fp']:>6}\n"
        f"Actual 1      {matrix['fn']:>6} | {matrix['tp']:>6}\n"
    )


def evaluate_model_suite(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = TRAINING_DIR / "output",
    model_path: str | Path = DEFAULT_MODEL_PATH,
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
) -> Dict[str, Any]:
    """Evaluate the trained models against train, validation, and held-out test data."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    model_path = Path(model_path)
    metadata_path = Path(metadata_path)

    train_df = pd.read_csv(data_dir / "train.csv")
    val_df = pd.read_csv(data_dir / "val.csv")
    test_df = pd.read_csv(data_dir / "test.csv")

    model_data = _load_pickle(model_path)
    metadata = _load_metadata(metadata_path)
    models: Dict[str, Any] = model_data.get("models", {})
    metrics: Dict[str, Dict[str, Any]] = model_data.get("metrics", {})
    statuses: Dict[str, str] = model_data.get("model_status", {})

    patient_features = ["organism", "age", "gender", "kidney_function", "severity"]
    antibiotic_names = list(metrics.keys())

    rows: List[Dict[str, Any]] = []
    test_report: List[Dict[str, Any]] = []
    confusion_reports: Dict[str, Dict[str, int]] = {}

    for antibiotic in antibiotic_names:
        model = models.get(antibiotic)
        status = statuses.get(antibiotic, metrics.get(antibiotic, {}).get("status", "included"))

        train_auc = None
        val_auc = float(metrics.get(antibiotic, {}).get("auc", 0.0))
        test_auc = None
        test_accuracy = None
        test_f1 = None

        if model is not None:
            for split_name, split_df in (("train", train_df), ("val", val_df), ("test", test_df)):
                if antibiotic not in split_df.columns:
                    continue

                y_true = split_df[antibiotic]
                if len(np.unique(y_true)) < 2:
                    continue

                probabilities = model.predict_proba(split_df[patient_features])[:, 1]
                auc = _safe_auc(y_true, probabilities)

                if split_name == "train":
                    train_auc = auc
                elif split_name == "test":
                    test_auc = auc
                    predictions = (probabilities >= 0.5).astype(int)
                    test_accuracy = float(accuracy_score(y_true, predictions))
                    test_f1 = float(f1_score(y_true, predictions, zero_division=0))
                    tn, fp, fn, tp = confusion_matrix(y_true, predictions).ravel()
                    confusion_reports[antibiotic] = {
                        "tn": int(tn),
                        "fp": int(fp),
                        "fn": int(fn),
                        "tp": int(tp),
                    }

        rows.append(
            {
                "name": antibiotic,
                "train_auc": train_auc,
                "val_auc": val_auc,
                "test_auc": test_auc,
                "status": status,
            }
        )
        test_report.append(
            {
                "name": antibiotic,
                "status": status,
                "train_auc": train_auc,
                "val_auc": val_auc,
                "test_auc": test_auc,
                "test_accuracy": test_accuracy,
                "test_f1": test_f1,
                "confusion_matrix": confusion_reports.get(antibiotic),
            }
        )

    table = _format_table(rows)
    print("\nAntibiotic | Train AUC | Val AUC | Test AUC | Status")
    print(table)

    top_5 = sorted(
        [row for row in test_report if row["test_auc"] is not None],
        key=lambda row: row["test_auc"],
        reverse=True,
    )[:5]

    print("\nASCII Confusion Matrices (top 5 antibiotics by Test AUC)")
    for row in top_5:
        if row["confusion_matrix"]:
            print(_format_confusion_matrix(row["name"], row["confusion_matrix"]))

    report = {
        "trained_at": metadata.get("trained_at"),
        "training_samples": metadata.get("training_samples"),
        "n_antibiotics": metadata.get("n_antibiotics", len(rows)),
        "summary": {
            "mean_train_auc": float(np.mean([row["train_auc"] for row in rows if row["train_auc"] is not None])) if any(row["train_auc"] is not None for row in rows) else None,
            "mean_val_auc": float(np.mean([row["val_auc"] for row in rows if row["val_auc"] is not None])) if any(row["val_auc"] is not None for row in rows) else None,
            "mean_test_auc": float(np.mean([row["test_auc"] for row in rows if row["test_auc"] is not None])) if any(row["test_auc"] is not None for row in rows) else None,
        },
        "antibiotics": test_report,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print(f"\nSaved evaluation report to {report_path}")
    return report


if __name__ == "__main__":
    evaluate_model_suite()