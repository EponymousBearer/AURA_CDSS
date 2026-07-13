# AURA Localised Antibiograms — README

This folder holds **pluggable, per-locale antibiograms** that drive AURA's Layer-2 (filter + local %-susceptible priors). One file per locale:

- `us_armd.json` — derived from ARMD (the existing `organism_antibiotic_panel.json`, re-expressed in this schema). Default `locale`.
- `pakistan.json` — the localisation target (Route A). **Currently a single-centre SEED — must be upgraded to national data.**

`pakistan.schema.json` validates any locale file. See the companion `AURA_BUILD_ROADMAP.md` (milestone **M4**) for how this fits the build.

---

## 1. What this file is (and is NOT)

- It IS a structured antibiogram: for each `organism → drug`, the **local %-susceptible** plus provenance.
- It is NOT row-level patient data. The Pakistan recommendation path is **statistical/antibiogram-driven (Route A)**, because Pakistani AMR data is almost entirely aggregate. The US-trained RandomForest is **not** used to score `locale=pakistan` requests. (Row-level retrain = Route B = future work needing a hospital partnership + IRB.)

---

## 2. Cell semantics (the important rules)

Each `drugs.<drug>` cell:

| Field | Meaning |
|---|---|
| `percent_susceptible` | Local **%-SUSCEPTIBLE** (0–100). Store susceptibility, **not** resistance — convert with `100 − %R`. `null` only when `status="unknown"`. |
| `n_isolates` | Isolate count behind the number (for the `min_isolates_for_filter` rule). `null` if unknown. |
| `status` | `ok` = usable number · `unknown` = no local data · `do_not_use` = clinically gated OFF regardless of any number. |
| `tested` | Is the bug-drug pair locally tested/reportable at all? `false` ⇒ dropped by the filter. |
| `source_id` | Must match a `meta.sources[].id`, or `TODO` for placeholders. |
| `confidence` | `national_surveillance` > `multicenter` > `single_center` > `review_pooled` > `expert_flag` > `placeholder`. |

### The three statuses drive the engine
- **`ok`** → eligible; ranked by `percent_susceptible`.
- **`unknown`** → **excluded** from recommendations and surfaced to the UI as *"insufficient local data."* **Never** fall back to another locale's number (`meta.unknown_policy = "no_us_fallback"`). This is a deliberate safety choice: silence is safer than a US rate masquerading as a Pakistani one.
- **`do_not_use`** → **always excluded**, even if a % exists. Used for clinically gated agents (e.g. ceftriaxone/ciprofloxacin for XDR *S.* Typhi during the outbreak).

---

## 3. How the engine should consume it (Layer-2 contract)

For a `locale=pakistan` request on `(organism, …)`:

1. Look up `organisms[organism].drugs`.
2. **Filter out** any drug where `tested == false`, OR `status == "unknown"`, OR `status == "do_not_use"`, OR (`n_isolates != null` AND `n_isolates < meta.min_isolates_for_filter`).
3. **Rank** survivors by `percent_susceptible` (desc). Return Top-3 + full ranked list.
4. Attach provenance (`source_id`, `confidence`, `year`) to each returned drug so the UI can show *"based on single_center data, 2013–2022"* and flag low-confidence picks.
5. If the organism is absent, return an explicit *"no local antibiogram for this organism"* response — again, **no** US fallback.

> Optional stretch (Roadmap M4.3, Review §4(f)): instead of raw ranking, blend `percent_susceptible` as a **Bayesian prior** with the model likelihood. Keep `unknown`/`do_not_use` gating regardless.

---

## 4. Name alignment (do this before serving — it's the #1 integration gotcha)

The organism and drug **keys here are lowercase snake_case placeholders.** They MUST be mapped to:
- the **organism strings** the model/cohort actually uses (from the cohort CSV / `GET /api/v2/organisms`), and
- the model's **`antibiotic` feature names**.

Add a `name_map.json` (or extend the loader) that translates between the two, and add a **load-time check** that every key in `pakistan.json` resolves to a known organism/drug — fail fast if not. Do the same for `us_armd.json` so both locales share one vocabulary.

---

## 5. Fill-in workflow (how to take this from SEED → national)

1. **Pull the national tables.** Priority sources (Review §5a): Pakistan AMR Surveillance (NIH Pakistan) annual report, PARN antibiograms, WHO GLASS-Pakistan, SOAR 2018–21. These are aggregate and mostly open — manual transcription from PDFs is expected.
2. **For each `organism × drug`:** enter `percent_susceptible` (convert from %R if needed), `n_isolates`, set `status="ok"`, point `source_id` at the national source, and bump `confidence` to `national_surveillance`/`multicenter`.
3. **Resolve every placeholder:** search the file for `"source_id": "TODO_PARN_national"` and `"status": "unknown"` — each is an explicit data gap to close.
4. **Keep clinical gates:** leave `do_not_use` on XDR-Typhi ceftriaxone/ciprofloxacin/first-line agents unless national data clearly shows the outbreak strain has receded.
5. **Re-validate:** `python -c "import json,jsonschema; jsonschema.Draft202012Validator(json.load(open('pakistan.schema.json'))).validate(json.load(open('pakistan.json')))"`.
6. **Run the localisation tests** (Roadmap M4.4 `validate_localisation.py`): typhoid must not surface ceftriaxone; *E. coli* must down-rank 3rd-gen cephalosporins vs `us_armd`; `us_armd` output unchanged.
7. **Bump `meta.version`** and `meta.generated`, and downgrade the `display_name` warning once cells are national.

---

## 6. Current seed status (as shipped)

- **6 organisms, 45 cells:** 18 `ok`, 22 `unknown` (TODO), 5 `do_not_use`.
- Real cited anchors exist for **E. coli, K. pneumoniae, S. Typhi** (mostly single-centre).
- **Acinetobacter, Pseudomonas, S. aureus** are mostly placeholders — these are your highest-priority fills.
- **Provenance honesty:** every number traces to a `meta.sources` entry; nothing is invented. Single-centre values are flagged as such and should not be presented as national rates in the thesis without that caveat.

> Reminder: this is research/academic only — not a validated antibiogram for clinical prescribing.
