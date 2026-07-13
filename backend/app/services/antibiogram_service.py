"""
LocaleAntibiogramService (M4) — pluggable per-locale antibiograms.

Layer-2 becomes locale-aware. Each locale is one JSON file in backend/antibiograms/
(schema: antibiogram.schema.json):

  - us_armd.json   — US/ARMD antibiogram (generated from the cohort). The US
                     recommendation path still ranks with the RF model; this file
                     is used for the US-vs-PK contrast and provenance.
  - pakistan.json  — the localisation target (Route A). Because Pakistani AMR data
                     is aggregate-only, the Pakistan path is driven DIRECTLY by this
                     antibiogram (filter + rank by %-susceptible), NOT by the
                     US-trained RandomForest.

Contract implemented here mirrors ANTIBIOGRAM_README.md §3:
  filter out  tested==false | status 'unknown' | status 'do_not_use'
              | (n_isolates is not None and n_isolates < min_isolates_for_filter)
  rank survivors by percent_susceptible desc; attach provenance.
  'unknown'/'do_not_use' are NEVER back-filled from another locale (no_us_fallback).

Name alignment: antibiogram keys are snake_case; the model/cohort use lowercase
spaced strings. Matching is algorithmic (snake_case <-> spaced), with an optional
name_map.json override for edge cases. A load-time check logs any locale whose
organism keys fail to normalise.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Statuses/flags that gate a drug OFF regardless of any number.
_EXCLUDE_STATUSES = {'unknown', 'do_not_use'}


def _norm(s: str) -> str:
    """Canonical match key: lowercase, snake_case and spaces unified to spaces."""
    if s is None:
        return ''
    return ' '.join(str(s).strip().lower().replace('_', ' ').split())


def _display_drug(key: str) -> str:
    """Antibiogram snake_case drug key -> model-style spaced lowercase name."""
    return _norm(key)


class LocaleAntibiogramService:
    def __init__(self):
        self.locales: dict[str, dict] = {}          # locale -> full file dict
        self._org_index: dict[str, dict] = {}        # locale -> {norm(org): org_key}
        self.name_overrides: dict[str, str] = {}     # norm(input) -> norm(canonical)
        self._load()

    def _resolve_dir(self) -> Path:
        env = os.getenv('ANTIBIOGRAM_DIR')
        if env:
            return Path(env)
        # backend/app/services/antibiogram_service.py -> backend/antibiograms
        return Path(__file__).resolve().parent.parent.parent / 'antibiograms'

    def _load(self):
        d = self._resolve_dir()
        logger.info(f"Loading locale antibiograms from: {d}")
        if not d.exists():
            logger.warning(f"Antibiogram dir {d} not found; locale recommendations disabled.")
            return

        # optional name-map override
        nm = d / 'name_map.json'
        if nm.exists():
            try:
                raw = json.load(open(nm))
                self.name_overrides = {_norm(k): _norm(v) for k, v in raw.items()}
                logger.info(f"Loaded {len(self.name_overrides)} name-map overrides.")
            except Exception as exc:
                logger.error(f"Failed to read name_map.json: {exc}")

        for path in sorted(d.glob('*.json')):
            if path.name in ('antibiogram.schema.json', 'name_map.json'):
                continue
            try:
                data = json.load(open(path))
            except Exception as exc:
                logger.error(f"Skipping {path.name}: invalid JSON ({exc})")
                continue
            locale = (data.get('meta') or {}).get('locale')
            organisms = data.get('organisms')
            if not locale or not isinstance(organisms, dict):
                logger.error(f"Skipping {path.name}: missing meta.locale or organisms.")
                continue
            self.locales[locale] = data
            self._org_index[locale] = {_norm(o): o for o in organisms}
            logger.info(
                f"  locale '{locale}' <- {path.name}: {len(organisms)} organisms "
                f"(v{data['meta'].get('version', '?')})"
            )
        if not self.locales:
            logger.warning("No locale antibiograms loaded.")

    # ---- public API ----
    def available_locales(self) -> list[str]:
        return sorted(self.locales)

    def has_locale(self, locale: str) -> bool:
        return locale in self.locales

    def _resolve_org_key(self, locale: str, organism: str) -> Optional[str]:
        idx = self._org_index.get(locale, {})
        key = _norm(organism)
        key = self.name_overrides.get(key, key)
        return idx.get(key)

    def organisms(self, locale: str) -> list[str]:
        """Display organism names available for a locale (for input validation/UI)."""
        data = self.locales.get(locale, {})
        out = []
        for org_key, org in (data.get('organisms') or {}).items():
            out.append(org.get('display_name') or _norm(org_key))
        return sorted(out)

    def organism_entries(self, locale: str) -> list[dict]:
        """Organism options for a locale as {name, display_name}.

        `name` is the RESOLVABLE identifier (normalised org key) — the value a
        client should send back as `organism`, since `recommend`/`is_valid_organism`
        resolve against the key index, not the (possibly longer) display name.
        """
        data = self.locales.get(locale, {})
        out = []
        for org_key, org in (data.get('organisms') or {}).items():
            out.append({
                'name': _norm(org_key),
                'display_name': org.get('display_name') or _norm(org_key),
            })
        return sorted(out, key=lambda e: e['display_name'])

    def is_valid_organism(self, locale: str, organism: str) -> bool:
        return self._resolve_org_key(locale, organism) is not None

    def recommend(self, locale: str, organism: str, top_k: int = 3) -> dict:
        """Filter + rank a locale antibiogram for one organism (ANTIBIOGRAM_README §3)."""
        data = self.locales.get(locale)
        if data is None:
            return {'locale': locale, 'organism': organism, 'found': False,
                    'reason': 'unknown_locale', 'recommendations': [], 'all': [], 'excluded': {}}

        meta = data.get('meta', {})
        min_iso = int(meta.get('min_isolates_for_filter', 30))
        org_key = self._resolve_org_key(locale, organism)
        if org_key is None:
            # No local antibiogram for this organism — explicit, NO cross-locale fallback.
            return {'locale': locale, 'organism': organism, 'found': False,
                    'reason': 'no_local_antibiogram', 'recommendations': [], 'all': [],
                    'excluded': {}, 'meta': _meta_public(meta)}

        drugs = data['organisms'][org_key].get('drugs', {})
        kept, excluded = [], {}
        for drug_key, c in drugs.items():
            name = _display_drug(drug_key)
            if c.get('tested') is False:
                excluded[name] = 'not_tested'; continue
            if c.get('status') in _EXCLUDE_STATUSES:
                excluded[name] = f"gated_{c.get('status')}"; continue
            n = c.get('n_isolates')
            if n is not None and n < min_iso:
                excluded[name] = f"below_threshold(n={n})"; continue
            pct = c.get('percent_susceptible')
            if pct is None:
                excluded[name] = 'no_value'; continue
            kept.append({
                'antibiotic': name,
                'percent_susceptible': float(pct),
                'probability': round(float(pct) / 100.0, 4),
                'source_id': c.get('source_id'),
                'confidence': c.get('confidence'),
                'year': c.get('year'),
                'basis': 'antibiogram',
                'note': c.get('note'),
            })
        kept.sort(key=lambda r: r['percent_susceptible'], reverse=True)
        return {
            'locale': locale,
            'organism': organism,
            'organism_key': org_key,
            'found': True,
            'recommendations': kept[:top_k],
            'all': kept,
            'excluded': excluded,
            'meta': _meta_public(meta),
            'organism_notes': data['organisms'][org_key].get('notes'),
        }

    def get_cell(self, locale: str, organism: str, drug: str) -> Optional[dict]:
        """Raw cell for a (locale, organism, drug) — used by the US-vs-PK contrast."""
        data = self.locales.get(locale)
        if not data:
            return None
        org_key = self._resolve_org_key(locale, organism)
        if org_key is None:
            return None
        drugs = data['organisms'][org_key].get('drugs', {})
        want = _norm(drug)
        for k, c in drugs.items():
            if _norm(k) == want:
                return c
        return None


def _meta_public(meta: dict) -> dict:
    return {
        'display_name': meta.get('display_name'),
        'version': meta.get('version'),
        'breakpoint_standard': meta.get('breakpoint_standard'),
        'unknown_policy': meta.get('unknown_policy'),
        'min_isolates_for_filter': meta.get('min_isolates_for_filter'),
    }
