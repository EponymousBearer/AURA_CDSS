"""Culture-site and organism catalog for ARMD v2 validation."""

from pathlib import Path
import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)


class ClinicalCatalogService:
    """Builds a lightweight culture -> organism catalog from the ARMD cohort."""

    def __init__(self, top_n_organisms: int = 40):
        self.top_n_organisms = top_n_organisms
        self.catalog: dict[str, list[str]] = {}
        self.culture_sites: list[str] = []
        self._load_catalog()

    def _resolve_dataset_path(self) -> Path:
        env_path = os.getenv('ARMD_COHORT_PATH')
        if env_path:
            return Path(env_path)
        this_file = Path(__file__).resolve()
        project_root = this_file.parent.parent.parent.parent
        return project_root / 'datasets' / 'microbiology_cultures_cohort.csv'

    def _normalize(self, value: str | None) -> str:
        return str(value or '').strip().lower()

    def _load_catalog(self) -> None:
        cohort_path = self._resolve_dataset_path()
        fallback = {
            'blood': ['escherichia coli', 'klebsiella pneumoniae', 'staphylococcus aureus', 'enterococcus faecalis', 'other'],
            'urine': ['escherichia coli', 'klebsiella pneumoniae', 'proteus mirabilis', 'pseudomonas aeruginosa', 'other'],
            'respiratory': ['pseudomonas aeruginosa', 'staphylococcus aureus', 'klebsiella pneumoniae', 'other'],
        }

        if not cohort_path.exists():
            logger.warning("ARMD cohort not found at %s; using fallback clinical catalog", cohort_path)
            self.catalog = fallback
            self.culture_sites = sorted(fallback)
            return

        try:
            df = pd.read_csv(cohort_path, usecols=['culture_description', 'organism'])
            df['culture_description'] = df['culture_description'].map(self._normalize)
            df['organism'] = df['organism'].map(self._normalize)
            df = df[
                (df['culture_description'] != '') &
                (df['organism'] != '') &
                (df['organism'] != 'null')
            ]

            top_organisms = set(df['organism'].value_counts().head(self.top_n_organisms).index)
            catalog: dict[str, list[str]] = {}
            for culture_site, group in df.groupby('culture_description'):
                organisms = sorted(set(group['organism']).intersection(top_organisms))
                catalog[culture_site] = organisms + ['other']

            self.catalog = catalog or fallback
            self.culture_sites = sorted(self.catalog)
            logger.info("Loaded ARMD clinical catalog: culture_sites=%s", len(self.culture_sites))
        except Exception as exc:
            logger.warning("Failed to load ARMD clinical catalog: %s; using fallback", exc)
            self.catalog = fallback
            self.culture_sites = sorted(fallback)

    def get_catalog(self, culture_description: str | None = None) -> dict:
        culture = self._normalize(culture_description)
        if culture:
            organisms = self.catalog.get(culture, [])
            return {
                'culture_sites': self.culture_sites,
                'culture_description': culture,
                'organisms': organisms,
            }

        return {
            'culture_sites': self.culture_sites,
            'organisms_by_culture': self.catalog,
        }

    def is_valid_culture_site(self, culture_description: str) -> bool:
        return self._normalize(culture_description) in self.catalog

    def is_valid_organism_for_culture(self, culture_description: str, organism: str) -> bool:
        culture = self._normalize(culture_description)
        normalized_organism = self._normalize(organism)
        return normalized_organism in set(self.catalog.get(culture, []))
