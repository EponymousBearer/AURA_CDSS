#!/usr/bin/env python3
"""
validate_localisation.py  (Roadmap M4.4)
========================================
Locks in the clinically critical localisation invariants so no future refactor
can silently break them:

  PK1  Pakistan + S. Typhi  ->  ceftriaxone & fluoroquinolones NEVER recommended
                                (XDR outbreak); azithromycin/meropenem ARE.
  PK2  Pakistan + E. coli   ->  3rd-gen cephalosporins down-ranked vs carbapenems,
                                and lower %-susceptible than the US locale.
  PK3  Pakistan unknown-cells excluded; NO fall-back to US numbers.
  US1  us_armd FILTER set is stable (regression guard / golden snapshot).
  GEN  every antibiogram file validates against the schema and shares vocabulary.

HOW TO RUN
  python validate_localisation.py            # plain runner, prints PASS/FAIL
  pytest validate_localisation.py            # also works (test_* functions)

WHAT IT TESTS AGAINST
  By default it uses the REFERENCE Layer-2 consumer below, which implements the
  contract in ANTIBIOGRAM_README §3. To test the REAL engine instead, implement
  `engine_recommend()` in the ADAPTER block to call ARMDPredictorService and set
  USE_REAL_ENGINE = True. The invariants are identical either way.

FILES (override via env: PK_FILE, US_FILE, SCHEMA_FILE, GOLDEN_FILE)
  pakistan.json, us_armd.json, pakistan.schema.json, us_armd.filterset.golden.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Locale antibiograms live in backend/antibiograms/ (relocated in M4/T4.0).
ANTIBIOGRAM_DIR = os.path.join(HERE, os.pardir, "antibiograms")
PK_FILE     = os.environ.get("PK_FILE",     os.path.join(ANTIBIOGRAM_DIR, "pakistan.json"))
US_FILE     = os.environ.get("US_FILE",     os.path.join(ANTIBIOGRAM_DIR, "us_armd.json"))
SCHEMA_FILE = os.environ.get("SCHEMA_FILE", os.path.join(ANTIBIOGRAM_DIR, "antibiogram.schema.json"))
GOLDEN_FILE = os.environ.get("GOLDEN_FILE", os.path.join(HERE, "us_armd.filterset.golden.json"))

USE_REAL_ENGINE = True  # exercises the live LocaleAntibiogramService (engine_recommend below)


# ---------------------------------------------------------------------------
# REFERENCE Layer-2 consumer  (mirror of ANTIBIOGRAM_README §3)
# ---------------------------------------------------------------------------
def survivors(locale_data, organism):
    """Return {drug: cell} that PASS the filter for this organism, plus the set
    of excluded drugs with reasons. Implements the filter contract exactly."""
    min_iso = locale_data["meta"].get("min_isolates_for_filter", 30)
    org = locale_data["organisms"].get(organism)
    if org is None:
        return {}, {"_organism": "no_local_antibiogram"}
    kept, excluded = {}, {}
    for drug, c in org["drugs"].items():
        if c.get("tested") is False:
            excluded[drug] = "not_tested"; continue
        if c.get("status") == "unknown":
            excluded[drug] = "unknown_no_fallback"; continue
        if c.get("status") == "do_not_use":
            excluded[drug] = "do_not_use_clinical_gate"; continue
        n = c.get("n_isolates")
        if n is not None and n < min_iso:
            excluded[drug] = f"below_threshold(n={n})"; continue
        kept[drug] = c
    return kept, excluded


def recommend(locale_data, organism, model_scores=None, top_k=3):
    """Filter then rank. US path ranks by model score if given; otherwise (PK
    path / no model) ranks by local %-susceptible. Returns ordered drug list."""
    kept, excluded = survivors(locale_data, organism)
    if model_scores:
        ranked = sorted(kept, key=lambda d: model_scores.get(d, -1), reverse=True)
    else:
        ranked = sorted(kept, key=lambda d: (kept[d].get("percent_susceptible") or -1), reverse=True)
    return {"top_k": ranked[:top_k], "ranked": ranked, "excluded": excluded, "cells": kept}


# ---------------------------------------------------------------------------
# ADAPTER — wire the REAL engine here, then set USE_REAL_ENGINE = True
# ---------------------------------------------------------------------------
_ENGINE = None


def engine_recommend(locale, organism, top_k=3):
    """Ordered recommended drug keys from the REAL LocaleAntibiogramService.

    Returns the full ranked list (underscore-normalised to match the test's
    GATED/CEPH vocabularies, e.g. 'trimethoprim_sulfamethoxazole')."""
    global _ENGINE
    if _ENGINE is None:
        from app.services.antibiogram_service import LocaleAntibiogramService
        _ENGINE = LocaleAntibiogramService()
    rec = _ENGINE.recommend(locale, organism, top_k=top_k)
    return [r["antibiotic"].replace(" ", "_") for r in rec["all"]]


def get_reco(locale_data, locale_name, organism, model_scores=None, top_k=3):
    if USE_REAL_ENGINE:
        ranked = engine_recommend(locale_name, organism, top_k)
        return {"top_k": ranked[:top_k], "ranked": ranked}
    return recommend(locale_data, organism, model_scores=model_scores, top_k=top_k)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load(path):
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def ensure_us_file():
    """Use the real us_armd.json if present; otherwise synthesise an illustrative
    one (clearly flagged) so US-side tests can still demonstrate the logic."""
    us = load(US_FILE)
    if us is not None:
        return us, True
    print(f"NOTE: {os.path.basename(US_FILE)} not found — using an ILLUSTRATIVE "
          f"synthetic US antibiogram. Generate the real one with "
          f"build_us_armd_antibiogram.py for a meaningful regression guard.")
    return {
        "meta": {"locale": "us_armd", "version": "synthetic", "breakpoint_standard": "CLSI",
                 "min_isolates_for_filter": 30, "unknown_policy": "no_us_fallback",
                 "sources": [{"id": "synthetic", "citation": "illustrative"}]},
        "organisms": {
            "escherichia_coli": {"drugs": {
                "ceftriaxone": {"percent_susceptible": 90, "n_isolates": 500, "status": "ok",
                                "tested": True, "source_id": "synthetic", "confidence": "placeholder"},
                "meropenem":   {"percent_susceptible": 99, "n_isolates": 500, "status": "ok",
                                "tested": True, "source_id": "synthetic", "confidence": "placeholder"},
                "nitrofurantoin": {"percent_susceptible": 96, "n_isolates": 500, "status": "ok",
                                "tested": True, "source_id": "synthetic", "confidence": "placeholder"},
            }},
            "salmonella_typhi": {"drugs": {
                "ceftriaxone": {"percent_susceptible": 99, "n_isolates": 200, "status": "ok",
                                "tested": True, "source_id": "synthetic", "confidence": "placeholder"},
            }},
        },
    }, False


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------
GATED_FOR_TYPHI = {"ceftriaxone", "cefotaxime", "ciprofloxacin", "levofloxacin",
                   "ampicillin", "chloramphenicol", "trimethoprim_sulfamethoxazole"}
THIRD_GEN_CEPHS = {"ceftriaxone", "cefotaxime", "ceftazidime"}
CARBAPENEMS     = {"meropenem", "imipenem", "ertapenem"}


def test_PK1_typhoid_never_ceftriaxone():
    pk = load(PK_FILE); assert pk, f"missing {PK_FILE}"
    r = get_reco(pk, "pakistan", "salmonella_typhi", top_k=3)
    full = set(r.get("ranked", r["top_k"]))
    for drug in GATED_FOR_TYPHI:
        assert drug not in full, f"PK1 FAIL: {drug} must never be recommended for PK typhoid"
    assert "azithromycin" in full, "PK1 FAIL: azithromycin should be available"
    assert any(d in full for d in ("meropenem", "imipenem")), "PK1 FAIL: a carbapenem should be available"
    # the reliable options should top the list
    assert r["top_k"][0] in CARBAPENEMS | {"azithromycin"}, f"PK1 FAIL: unexpected top pick {r['top_k']}"


def test_PK2_ecoli_cephalosporins_downranked():
    pk = load(PK_FILE); assert pk, f"missing {PK_FILE}"
    r = recommend(pk, "escherichia_coli", top_k=3)
    ranked = r["ranked"]
    # no 3rd-gen ceph should appear in Top-3 (carbapenems/nitro/colistin dominate)
    assert not (set(r["top_k"]) & THIRD_GEN_CEPHS), f"PK2 FAIL: 3rd-gen ceph in Top-3: {r['top_k']}"
    # every present carbapenem must out-rank every present 3rd-gen ceph
    pos = {d: i for i, d in enumerate(ranked)}
    for cb in CARBAPENEMS & set(pos):
        for ce in THIRD_GEN_CEPHS & set(pos):
            assert pos[cb] < pos[ce], f"PK2 FAIL: {ce} ranked above {cb}"


def test_PK2b_ecoli_ceftriaxone_lower_than_us():
    pk = load(PK_FILE); assert pk
    us, real = ensure_us_file()
    pk_cell = pk["organisms"]["escherichia_coli"]["drugs"].get("ceftriaxone", {})
    us_cell = us["organisms"]["escherichia_coli"]["drugs"].get("ceftriaxone", {})
    pk_s, us_s = pk_cell.get("percent_susceptible"), us_cell.get("percent_susceptible")
    assert pk_s is not None and us_s is not None, "need ceftriaxone %S in both locales"
    assert pk_s < us_s, f"PK2b FAIL: PK ceftriaxone %S ({pk_s}) should be < US ({us_s})"
    print(f"      PK2b: E. coli ceftriaxone %S  PK={pk_s}  US={us_s}  ({'real' if real else 'synthetic US'})")


def test_PK3_unknown_no_fallback():
    pk = load(PK_FILE); assert pk
    _, excluded = survivors(pk, "escherichia_coli")
    # ciprofloxacin is status:unknown in the seed -> must be excluded, never US-filled
    assert excluded.get("ciprofloxacin") == "unknown_no_fallback", \
        f"PK3 FAIL: unknown cell not excluded correctly: {excluded.get('ciprofloxacin')}"


def test_US1_filterset_regression():
    us, real = ensure_us_file()
    if not real:
        print("      US1: skipped (no real us_armd.json — generate it for a real guard).")
        return
    current = {org: sorted(survivors(us, org)[0].keys()) for org in us["organisms"]}
    golden = load(GOLDEN_FILE)
    if golden is None:
        json.dump(current, open(GOLDEN_FILE, "w"), indent=2, sort_keys=True)
        print(f"      US1: wrote initial golden snapshot -> {os.path.basename(GOLDEN_FILE)}. "
              f"Commit it; future runs compare against it.")
        return
    assert current == golden, ("US1 FAIL: us_armd filter set changed vs golden snapshot. "
                               "If intentional, delete the golden file and re-run to regenerate.")


def test_GEN_schema_and_vocabulary():
    schema = load(SCHEMA_FILE)
    if schema is None:
        print("      GEN: schema file absent — skipping validation."); return
    try:
        import jsonschema
    except ImportError:
        print("      GEN: jsonschema not installed — skipping validation."); return
    v = jsonschema.Draft202012Validator(schema)
    for path in (PK_FILE, US_FILE):
        data = load(path)
        if data is None:
            continue
        v.validate(data)
    # shared-vocabulary smoke check: PK drug keys should look normalised (snake_case)
    pk = load(PK_FILE)
    for org, ov in pk["organisms"].items():
        for drug in ov["drugs"]:
            assert drug == drug.lower() and " " not in drug, f"GEN FAIL: non-normalised key '{drug}'"


# ---------------------------------------------------------------------------
# plain runner (no pytest needed)
# ---------------------------------------------------------------------------
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}\n      {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}\n      {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
