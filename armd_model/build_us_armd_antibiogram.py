#!/usr/bin/env python3
"""
build_us_armd_antibiogram.py
============================
Re-express AURA's existing ARMD antibiogram in the pluggable locale-antibiogram
schema (the same one `pakistan.json` uses), producing `us_armd.json`.

WHY: Roadmap M4.1 makes Layer-2 antibiogram-pluggable. For the US path the
antibiogram is primarily a FILTER (which organism x drug pairs are tested,
>= CLSI M39 threshold). This script also computes %-susceptible per cell so the
US-vs-Pakistan contrast chart (M6.3) and optional Bayesian priors (M4.3) have
real US numbers. Ranking in the US path still comes from the RF model; this file
governs filtering + provenance, exactly like the current organism_antibiotic_panel.json.

SOURCE OF TRUTH:
  - cohort CSV  -> %-susceptible + isolate counts (the real data)
  - panel JSON  -> (optional) the authoritative set of valid pairs; used to
                   RECONCILE so the filter set matches current behaviour
                   (the "byte-for-byte unchanged us_armd output" regression guard).

USAGE:
  python build_us_armd_antibiogram.py \
      --cohort microbiology_cultures_cohort.csv \
      --panel  organism_antibiotic_panel.json \
      --out    us_armd.json \
      --schema pakistan.schema.json            # optional: validate output

  # cohort-only (recompute everything from data):
  python build_us_armd_antibiogram.py --cohort cohort.csv --out us_armd.json

  # self-test on synthetic data (no real files needed):
  python build_us_armd_antibiogram.py --selftest

ADJUST THE CONFIG BLOCK BELOW to match your actual cohort column names and the
value(s) that encode "susceptible". The script fails loudly if columns are missing.
"""

import argparse
import json
import sys
import tempfile
import os
from collections import defaultdict

# ----------------------------------------------------------------------------
# CONFIG — edit to match your cohort CSV
# ----------------------------------------------------------------------------
CONFIG = {
    # Column names in microbiology_cultures_cohort.csv
    "col_organism": "organism",
    "col_antibiotic": "antibiotic",
    # The susceptibility target column. ARMD dossier says binary (1=susceptible,0=not).
    # If your column is text ('Susceptible'/'Resistant'/'Intermediate' or 'S'/'I'/'R'),
    # the script auto-detects and uses SUSCEPTIBLE_VALUES below.
    "col_susceptible": "susceptibility",

    # Values counted as "susceptible". Numeric 1 OR these strings (case-insensitive).
    "susceptible_values": {"1", "s", "susceptible", "sensitive"},
    # Values counted as "intermediate" — by default NOT counted as susceptible.
    # Set count_intermediate_as_susceptible=True to fold I into S (some labs do).
    "intermediate_values": {"i", "intermediate"},
    "count_intermediate_as_susceptible": False,

    # CLSI M39: minimum isolates for a cell to be reportable.
    "min_isolates": 30,

    # Provenance for every US cell.
    "source_id": "armd",
    "source_citation": ("ARMD — Antibiotic Resistance Microbiology Dataset, Stanford "
                        "Health Care (~970k cultures, ~15 yrs). Nature Scientific Data (2025)."),
    "source_url": "",  # fill with the ARMD Sci Data DOI/URL
    "source_granularity": "single_center",  # one health system
    "source_years": "~2009-2023",
    "cell_confidence": "single_center",
    "breakpoint_standard": "CLSI",
}


def normalize_key(s: str) -> str:
    """Lowercase snake_case key. MUST stay consistent with pakistan.json keys
    and the model's organism/antibiotic vocab (see ANTIBIOGRAM_README §4)."""
    s = str(s).strip().lower()
    for ch in [" ", "-", "/", ".", ",", "(", ")"]:
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def classify(value, cfg) -> str:
    """Return 'S', 'I', or 'R' for a raw susceptibility cell value."""
    v = str(value).strip().lower()
    if v in cfg["susceptible_values"]:
        return "S"
    if v in cfg["intermediate_values"]:
        return "I"
    return "R"


def build_cells_from_cohort(df, cfg):
    """Aggregate cohort rows -> {organism: {drug: {n, n_susc}}}."""
    for col in (cfg["col_organism"], cfg["col_antibiotic"], cfg["col_susceptible"]):
        if col not in df.columns:
            sys.exit(f"ERROR: column '{col}' not found in cohort. "
                     f"Available: {list(df.columns)}. Edit CONFIG.")
    agg = defaultdict(lambda: defaultdict(lambda: {"n": 0, "n_susc": 0}))
    for org, drug, susc in zip(df[cfg["col_organism"]],
                               df[cfg["col_antibiotic"]],
                               df[cfg["col_susceptible"]]):
        if org is None or drug is None or str(org).strip() == "" or str(drug).strip() == "":
            continue
        ok = classify(susc, cfg)
        if str(susc).strip().lower() in ("", "nan", "null", "none"):
            continue
        cell = agg[normalize_key(org)][normalize_key(drug)]
        cell["n"] += 1
        is_s = (ok == "S") or (ok == "I" and cfg["count_intermediate_as_susceptible"])
        cell["n_susc"] += 1 if is_s else 0
    return agg


def load_panel_pairs(panel_path):
    """Best-effort extraction of valid (organism, drug) pairs from an existing
    organism_antibiotic_panel.json, whatever its shape. Returns a set of
    (normalized_org, normalized_drug)."""
    data = json.load(open(panel_path))
    pairs = set()

    def add(org, drug):
        pairs.add((normalize_key(org), normalize_key(drug)))

    if isinstance(data, dict):
        for org, drugs in data.items():
            if isinstance(drugs, dict):
                for drug in drugs.keys():
                    add(org, drug)
            elif isinstance(drugs, (list, tuple, set)):
                for drug in drugs:
                    add(org, drug)
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                o = row.get("organism") or row.get("org")
                d = row.get("antibiotic") or row.get("drug")
                if o and d:
                    add(o, d)
    if not pairs:
        print("WARN: could not parse any pairs from panel JSON; "
              "reconciliation skipped (unknown shape).", file=sys.stderr)
    return pairs


def assemble(agg, cfg, restrict_pairs=None, include_subthreshold=False):
    """Turn aggregates into the schema instance."""
    organisms = {}
    stats = {"cells_ok": 0, "cells_subthreshold": 0, "dropped_by_panel": 0}
    for org, drugs in sorted(agg.items()):
        out_drugs = {}
        for drug, c in sorted(drugs.items()):
            if restrict_pairs is not None and (org, drug) not in restrict_pairs:
                stats["dropped_by_panel"] += 1
                continue
            pct = round(100.0 * c["n_susc"] / c["n"], 1) if c["n"] else None
            below = c["n"] < cfg["min_isolates"]
            if below and not include_subthreshold:
                stats["cells_subthreshold"] += 1
                continue
            out_drugs[drug] = {
                "percent_susceptible": pct if not below else (pct if include_subthreshold else None),
                "n_isolates": c["n"],
                "status": "ok" if not below else "unknown",
                "tested": True if not below else False,
                "source_id": cfg["source_id"],
                "year": cfg["source_years"],
                "confidence": cfg["cell_confidence"],
            }
            if below:
                out_drugs[drug]["percent_susceptible"] = None
                out_drugs[drug]["note"] = f"Below {cfg['min_isolates']}-isolate CLSI M39 threshold (n={c['n']}); not reportable."
                stats["cells_subthreshold"] += 1
            else:
                stats["cells_ok"] += 1
        if out_drugs:
            organisms[org] = {"display_name": org.replace("_", " ").title(), "drugs": out_drugs}
    instance = {
        "meta": {
            "locale": "us_armd",
            "display_name": "United States — ARMD (Stanford) proof-of-method antibiogram",
            "version": "1.0.0",
            "generated": __import__("datetime").date.today().isoformat(),
            "breakpoint_standard": cfg["breakpoint_standard"],
            "min_isolates_for_filter": cfg["min_isolates"],
            "unknown_policy": "no_us_fallback",
            "sources": [{
                "id": cfg["source_id"],
                "citation": cfg["source_citation"],
                "url": cfg["source_url"],
                "granularity": cfg["source_granularity"],
                "years": cfg["source_years"],
            }],
            "notes": ("Auto-generated from the ARMD cohort by build_us_armd_antibiogram.py. "
                      "In the US path the RF model drives ranking; this antibiogram drives the "
                      "FILTER (tested pairs >= CLSI M39 threshold) and supplies US %-susceptible "
                      "for the US-vs-PK contrast chart. Keys are normalised snake_case and must "
                      "share the vocabulary used by pakistan.json and the model (see README)."),
        },
        "organisms": organisms,
    }
    return instance, stats


def maybe_validate(instance, schema_path):
    if not schema_path:
        return
    try:
        import jsonschema
    except ImportError:
        print("WARN: jsonschema not installed; skipping validation "
              "(pip install jsonschema).", file=sys.stderr)
        return
    schema = json.load(open(schema_path))
    jsonschema.Draft202012Validator(schema).validate(instance)
    print("VALID: output conforms to schema.")


def run(cohort_path, panel_path, out_path, schema_path, include_subthreshold):
    import pandas as pd
    df = pd.read_csv(cohort_path, dtype=str, keep_default_na=False, na_values=["Null"])
    agg = build_cells_from_cohort(df, CONFIG)
    restrict = load_panel_pairs(panel_path) if panel_path else None
    instance, stats = assemble(agg, CONFIG, restrict_pairs=restrict,
                               include_subthreshold=include_subthreshold)
    json.dump(instance, open(out_path, "w"), indent=2)
    print(f"Wrote {out_path}: {len(instance['organisms'])} organisms, "
          f"{stats['cells_ok']} reportable cells, "
          f"{stats['cells_subthreshold']} sub-threshold, "
          f"{stats['dropped_by_panel']} dropped-by-panel.")
    if restrict is not None:
        # reconciliation report
        derived = {(o, d) for o, ds in agg.items() for d in ds}
        only_panel = restrict - derived
        if only_panel:
            print(f"RECONCILE WARN: {len(only_panel)} pairs in panel but NOT in cohort "
                  f"(e.g. {list(sorted(only_panel))[:5]}). Investigate before trusting parity.")
    maybe_validate(instance, schema_path)


def selftest():
    """Generate synthetic cohort + panel, run end-to-end, validate."""
    import pandas as pd
    rows = []
    # E. coli: 40 ampicillin (10 S), 40 meropenem (38 S), 5 colistin (sub-threshold)
    rows += [("Escherichia coli", "Ampicillin", "1")] * 10 + [("Escherichia coli", "Ampicillin", "0")] * 30
    rows += [("Escherichia coli", "Meropenem", "Susceptible")] * 38 + [("Escherichia coli", "Meropenem", "Resistant")] * 2
    rows += [("Escherichia coli", "Colistin", "S")] * 5
    # K. pneumoniae: 50 ceftriaxone (15 S), 35 imipenem (22 S, 3 I)
    rows += [("Klebsiella pneumoniae", "Ceftriaxone", "1")] * 15 + [("Klebsiella pneumoniae", "Ceftriaxone", "0")] * 35
    rows += [("Klebsiella pneumoniae", "Imipenem", "S")] * 22 + [("Klebsiella pneumoniae", "Imipenem", "I")] * 3 + [("Klebsiella pneumoniae", "Imipenem", "R")] * 10
    df = pd.DataFrame(rows, columns=["organism", "antibiotic", "susceptibility"])

    d = tempfile.mkdtemp()
    cohort = os.path.join(d, "cohort.csv"); df.to_csv(cohort, index=False)
    panel = os.path.join(d, "panel.json")
    json.dump({"escherichia_coli": ["ampicillin", "meropenem"],
               "klebsiella_pneumoniae": ["ceftriaxone", "imipenem"]}, open(panel, "w"))
    out = os.path.join(d, "us_armd.json")
    schema = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pakistan.schema.json")
    schema = schema if os.path.exists(schema) else None

    print("--- SELFTEST: cohort + panel reconciliation ---")
    run(cohort, panel, out, schema, include_subthreshold=False)
    inst = json.load(open(out))
    ec = inst["organisms"]["escherichia_coli"]["drugs"]
    kp = inst["organisms"]["klebsiella_pneumoniae"]["drugs"]
    assert ec["ampicillin"]["percent_susceptible"] == 25.0, ec["ampicillin"]
    assert ec["meropenem"]["percent_susceptible"] == 95.0, ec["meropenem"]
    assert "colistin" not in ec, "colistin (n=5) should be filtered sub-threshold"
    assert kp["ceftriaxone"]["percent_susceptible"] == 30.0, kp["ceftriaxone"]
    # imipenem: 22 S of 35, I not counted as S -> 62.9
    assert kp["imipenem"]["percent_susceptible"] == 62.9, kp["imipenem"]
    print("SELFTEST PASSED: counts, threshold filtering, and I-handling all correct.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", help="microbiology_cultures_cohort.csv")
    ap.add_argument("--panel", help="existing organism_antibiotic_panel.json (optional, for reconciliation)")
    ap.add_argument("--out", default="us_armd.json")
    ap.add_argument("--schema", help="pakistan.schema.json (optional, validates output)")
    ap.add_argument("--include-subthreshold", action="store_true",
                    help="emit sub-threshold pairs as tested:false/status:unknown for transparency")
    ap.add_argument("--selftest", action="store_true", help="run on synthetic data and exit")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if not args.cohort:
        ap.error("--cohort is required (or use --selftest)")
    run(args.cohort, args.panel, args.out, args.schema, args.include_subthreshold)


if __name__ == "__main__":
    main()
