"""
Data preprocessing module for antibiotic susceptibility prediction.
Handles data cleaning, feature encoding, and train/validation splits.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import logging

logger = logging.getLogger(__name__)

TRAINING_DIR = Path(__file__).resolve().parent

# Maps Dryad uppercase organism labels to canonical categories used by the app.
# Any organism not listed here is bucketed into "Other".
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


def get_dataset_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Collect a readable summary of the loaded dataset."""
    patient_feature_columns = {
        "anon_id",
        "organism",
        "age",
        "gender",
        "kidney_function",
        "severity",
    }
    antibiotic_columns = [column for column in df.columns if column not in patient_feature_columns]

    susceptibility_rates = {}
    for column in antibiotic_columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            susceptibility_rates[column] = round(float(df[column].mean() * 100), 2)

    missing_counts = df.isna().sum()
    missing_values_summary = {
        "total_missing_values": int(missing_counts.sum()),
        "columns_with_missing_values": {
            column: int(count)
            for column, count in missing_counts.items()
            if int(count) > 0
        },
    }

    return {
        "total_rows": int(len(df)),
        "organisms_found": sorted(df["organism"].dropna().astype(str).unique().tolist()) if "organism" in df.columns else [],
        "antibiotics_found": sorted(antibiotic_columns),
        "susceptibility_rates": susceptibility_rates,
        "missing_values_summary": missing_values_summary,
    }


def save_stats_report(stats: Dict[str, Any], output_path: str | Path) -> str:
    """Save dataset stats as a readable JSON report."""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".json":
        output_path = output_path / "dataset_report.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2)

    return str(output_path)


class DataPreprocessor:
    """
    Handles all data preprocessing steps for antibiotic susceptibility data.
    Includes feature encoding, categorical handling, and data splitting.
    """

    def __init__(self):
        self.label_encoders: Dict[str, LabelEncoder] = {}
        self.target_encoders: Dict[str, LabelEncoder] = {}
        self.categorical_features = ['organism', 'gender', 'kidney_function', 'severity']
        self.antibiotic_columns: List[str] = []

    def _resolve_path(self, path: str) -> Path:
        """Resolve a possibly relative path against the training directory."""
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return (TRAINING_DIR / candidate).resolve()

    def _load_default_training_csvs(self) -> Optional[pd.DataFrame]:
        """Load and merge default demographics + resistance CSVs from training directory."""
        demographics_path = TRAINING_DIR / "microbiology_cultures_demographics.csv"
        resistance_path = TRAINING_DIR / "microbiology_cultures_microbial_resistance.csv"

        if not demographics_path.exists() or not resistance_path.exists():
            return None

        logger.info(
            "Loading default training CSVs: %s and %s",
            demographics_path.name,
            resistance_path.name,
        )

        demo = pd.read_csv(demographics_path)
        resistance = pd.read_csv(resistance_path)

        resistance["organism"] = (
            resistance["organism"]
            .astype(str)
            .str.strip()
            .str.upper()
            .map(ORGANISM_NORMALIZATION)
            .fillna("Other")
        )

        required_demo = {"anon_id", "age", "gender"}
        required_resistance = {"anon_id", "organism", "antibiotic"}
        if not required_demo.issubset(set(demo.columns)):
            logger.warning("Demographics CSV missing required columns, falling back to synthetic data")
            return None
        if not required_resistance.issubset(set(resistance.columns)):
            logger.warning("Resistance CSV missing required columns, falling back to synthetic data")
            return None

        demo = demo[list(required_demo)].drop_duplicates(subset=["anon_id"]).copy()
        resistance = resistance[list(required_resistance)].dropna(subset=["anon_id", "antibiotic"]).copy()

        # Convert age buckets like "25-34 years" to numeric midpoint for model training.
        age_numeric = (
            demo["age"].astype(str).str.extract(r"(\d+)-(\d+)")
            .astype(float)
            .mean(axis=1)
        )
        demo["age"] = age_numeric.fillna(50).round().astype(int)

        gender_map = {"1": "M", "2": "F", "M": "M", "F": "F", "Male": "M", "Female": "F"}
        demo["gender"] = demo["gender"].astype(str).map(gender_map).fillna("F")

        resistance["value"] = 1
        resistance_wide = (
            resistance.pivot_table(
                index="anon_id",
                columns="antibiotic",
                values="value",
                aggfunc="max",
                fill_value=0,
            )
            .reset_index()
        )

        organism_by_patient = (
            resistance.groupby("anon_id")["organism"]
            .agg(lambda values: values.mode().iloc[0] if not values.mode().empty else values.iloc[0])
            .reset_index()
        )

        df = demo.merge(organism_by_patient, on="anon_id", how="inner")
        df = df.merge(resistance_wide, on="anon_id", how="inner")

        if df.empty:
            logger.warning("Merged CSV dataset is empty, falling back to synthetic data")
            return None

        rng = np.random.default_rng(42)

        df["kidney_function"] = rng.choice(
            ["normal", "low", "severe"],
            size=len(df),
            p=[0.7, 0.2, 0.1],
        )

        age_values = df["age"].astype(float)
        severity_values = []
        for age in age_values:
            if age < 18 or age > 75:
                severity_values.append(
                    rng.choice(["high", "medium", "low"], p=[0.3, 0.6, 0.1])
                )
            else:
                severity_values.append(
                    rng.choice(["medium", "low", "high"], p=[0.6, 0.1, 0.3])
                )

        df["severity"] = severity_values

        # Keep expected patient feature columns first.
        patient_cols = ["organism", "age", "gender", "kidney_function", "severity"]
        antibiotic_cols = [c for c in df.columns if c not in {"anon_id", *patient_cols}]
        df = df[patient_cols + antibiotic_cols]

        stats = get_dataset_stats(df)
        report_path = save_stats_report(stats, TRAINING_DIR / "output" / "dataset_report.json")
        logger.info("Dataset stats: rows=%s organisms=%s antibiotics=%s report=%s", stats["total_rows"], len(stats["organisms_found"]), len(stats["antibiotics_found"]), report_path)

        logger.info("Loaded %s samples with %s antibiotic targets from default CSVs", len(df), len(antibiotic_cols))
        return df

    def load_data(self, file_path: str = None) -> pd.DataFrame:
        """
        Load data from CSV or generate synthetic data if no file provided.

        Args:
            file_path: Path to CSV file, if None generates synthetic data

        Returns:
            DataFrame with patient and antibiotic susceptibility data
        """
        if file_path:
            resolved_path = self._resolve_path(file_path)
            if resolved_path.exists():
                logger.info(f"Loading data from {resolved_path}")
                df = pd.read_csv(resolved_path)
                return df
            logger.warning("Provided data file not found at %s", resolved_path)

        default_df = self._load_default_training_csvs()
        if default_df is not None:
            return default_df

        logger.info("Generating synthetic training data")
        df = self._generate_synthetic_data()

        return df

    def _generate_synthetic_data(self, n_samples: int = 10000) -> pd.DataFrame:
        """
        Generate synthetic clinical data for training.

        Args:
            n_samples: Number of samples to generate

        Returns:
            DataFrame with synthetic patient and susceptibility data
        """
        np.random.seed(42)

        # Define possible values
        organisms = [
            'E. coli', 'K. pneumoniae', 'P. aeruginosa', 'A. baumannii',
            'S. aureus', 'E. faecium', 'S. pneumoniae', 'Enterococcus spp'
        ]
        genders = ['M', 'F']
        kidney_functions = ['normal', 'low']
        severities = ['low', 'medium', 'high']

        # Define antibiotics
        antibiotics = [
            'Amoxicillin', 'Amoxicillin-Clavulanate', 'Ampicillin', 'Piperacillin-Tazobactam',
            'Cefazolin', 'Ceftriaxone', 'Cefepime', 'Ceftazidime',
            'Meropenem', 'Imipenem', 'Ertapenem',
            'Ciprofloxacin', 'Levofloxacin', 'Moxifloxacin',
            'Gentamicin', 'Tobramycin', 'Amikacin',
            'Vancomycin', 'Linezolid', 'Daptomycin',
            'Tigecycline', 'Doxycycline', 'Minocycline',
            'Metronidazole', 'Clindamycin',
            'Trimethoprim-Sulfamethoxazole', 'Nitrofurantoin'
        ]

        data = {
            'organism': np.random.choice(organisms, n_samples),
            'age': np.random.randint(18, 90, n_samples),
            'gender': np.random.choice(genders, n_samples),
            'kidney_function': np.random.choice(kidney_functions, n_samples, p=[0.7, 0.3]),
            'severity': np.random.choice(severities, n_samples, p=[0.4, 0.4, 0.2]),
        }

        # Generate susceptibility based on organism-antibiotic relationships
        for abx in antibiotics:
            susceptibility = []
            for i in range(n_samples):
                organism = data['organism'][i]
                severity = data['severity'][i]

                # Base susceptibility by organism-antibiotic pairing
                base_prob = self._get_susceptibility_probability(organism, abx)

                # Adjust by severity (higher severity = more resistant infections)
                if severity == 'high':
                    base_prob *= 0.85
                elif severity == 'medium':
                    base_prob *= 0.95

                susceptibility.append(1 if np.random.random() < base_prob else 0)

            data[abx] = susceptibility

        df = pd.DataFrame(data)
        logger.info(f"Generated {n_samples} synthetic samples")
        return df

    def _get_susceptibility_probability(self, organism: str, antibiotic: str) -> float:
        """
        Get base susceptibility probability based on organism-antibiotic pairing.

        Args:
            organism: Bacterial organism name
            antibiotic: Antibiotic name

        Returns:
            Probability of susceptibility (0-1)
        """
        # Simplified resistance patterns based on typical microbiology
        resistance_patterns = {
            'E. coli': {
                'high': ['Ampicillin'],
                'medium': ['Amoxicillin', 'Ciprofloxacin'],
                'low': []
            },
            'K. pneumoniae': {
                'high': ['Ampicillin', 'Amoxicillin'],
                'medium': ['Ceftazidime', 'Cefepime', 'Ciprofloxacin'],
                'low': ['Meropenem', 'Imipenem']
            },
            'P. aeruginosa': {
                'high': ['Ampicillin', 'Amoxicillin', 'Amoxicillin-Clavulanate', 'Cefazolin',
                        'Ceftriaxone', 'Ciprofloxacin', 'Levofloxacin'],
                'medium': ['Piperacillin-Tazobactam', 'Ceftazidime', 'Cefepime'],
                'low': ['Meropenem', 'Amikacin', 'Tobramycin']
            },
            'A. baumannii': {
                'high': ['Ceftazidime', 'Cefepime', 'Ciprofloxacin', 'Levofloxacin',
                        'Gentamicin', 'Tobramycin'],
                'medium': ['Meropenem', 'Imipenem', 'Amikacin'],
                'low': ['Tigecycline', 'Minocycline']
            },
            'S. aureus': {
                'high': ['Ampicillin', 'Amoxicillin'],
                'medium': ['Ceftriaxone', 'Cefazolin'],
                'low': ['Vancomycin', 'Linezolid', 'Daptomycin']
            },
            'E. faecium': {
                'high': ['Ampicillin', 'Amoxicillin', 'Ciprofloxacin', 'Levofloxacin'],
                'medium': ['Vancomycin'],
                'low': ['Linezolid', 'Daptomycin']
            },
            'S. pneumoniae': {
                'high': [],
                'medium': ['Amoxicillin', 'Ampicillin'],
                'low': ['Ceftriaxone', 'Vancomycin', 'Linezolid']
            },
            'Enterococcus spp': {
                'high': ['Cefazolin', 'Ceftriaxone', 'Cefepime', 'Ceftazidime',
                         'Ciprofloxacin', 'Trimethoprim-Sulfamethoxazole'],
                'medium': ['Ampicillin', 'Amoxicillin'],
                'low': ['Vancomycin', 'Linezolid']
            }
        }

        # Default high susceptibility
        base_prob = 0.85

        if organism in resistance_patterns:
            patterns = resistance_patterns[organism]
            if antibiotic in patterns['high']:
                base_prob = 0.25
            elif antibiotic in patterns['medium']:
                base_prob = 0.55
            elif antibiotic in patterns['low']:
                base_prob = 0.95

        return base_prob

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare features for training.

        Args:
            df: Raw DataFrame

        Returns:
            Tuple of (features DataFrame, targets DataFrame)
        """
        # Identify antibiotic columns (all columns except patient features)
        patient_features = ['organism', 'age', 'gender', 'kidney_function', 'severity']
        self.antibiotic_columns = [col for col in df.columns if col not in patient_features]

        X = df[patient_features].copy()
        y = df[self.antibiotic_columns].copy()

        return X, y

    def split_data(self, X: pd.DataFrame, y: pd.DataFrame,
                   test_size: float = 0.2, val_size: float = 0.1
                   ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
                             pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Split data into train, validation, and test sets.

        Args:
            X: Features DataFrame
            y: Targets DataFrame
            test_size: Fraction for test set
            val_size: Fraction for validation set (from remaining data)

        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        # First split: separate test set
        X_temp, X_test, y_temp, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=None
        )

        # Second split: separate validation from remaining
        val_fraction = val_size / (1 - test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp, test_size=val_fraction, random_state=42, stratify=None
        )

        logger.info(f"Data split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")

        return X_train, X_val, X_test, y_train, y_val, y_test

    def get_feature_info(self) -> Dict[str, Any]:
        """
        Get information about features for model configuration.

        Returns:
            Dictionary with feature information
        """
        return {
            'categorical_features': self.categorical_features,
            'antibiotic_columns': self.antibiotic_columns,
            'n_antibiotics': len(self.antibiotic_columns)
        }


def preprocess_pipeline(output_dir: str = "./data") -> Tuple[str, str, Dict]:
    """
    Complete preprocessing pipeline.

    Args:
        output_dir: Directory to save processed data

    Returns:
        Tuple of (train_path, val_path, feature_info)
    """
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = (TRAINING_DIR / output_path).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    preprocessor = DataPreprocessor()

    # Load/generate data
    df = preprocessor.load_data()

    # Prepare features
    X, y = preprocessor.prepare_features(df)

    # Split data
    X_train, X_val, X_test, y_train, y_val, y_test = preprocessor.split_data(X, y)

    # Save processed data
    train_path = str(output_path / "train.csv")
    val_path = str(output_path / "val.csv")
    test_path = str(output_path / "test.csv")

    train_df = pd.concat([X_train, y_train], axis=1)
    val_df = pd.concat([X_val, y_val], axis=1)
    test_df = pd.concat([X_test, y_test], axis=1)

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    logger.info(f"Saved processed data to {output_path}")

    feature_info = preprocessor.get_feature_info()

    return train_path, val_path, test_path, feature_info


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    preprocess_pipeline()
