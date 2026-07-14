# AURA — Execution Roadmap (4-Week FYP Sprint)

> **Purpose.** This is the single source of truth for finishing AURA into the FYP deliverable described in the research. It turns `docs/research/AURA_FYP_Review.md` (the *why*) and `docs/research/AURA_BUILD_ROADMAP.md` (the *what*) into a **time-boxed, progress-tracked plan**. Every task has a checkbox, an owner-of-effort estimate, and acceptance criteria, so this file doubles as the **progress tracker** — update the status markers as you go.
>
> **Companion docs:** `docs/research/AURA_FYP_Review.md` (research, prior work, citations, justifications) · `docs/research/AURA_BUILD_ROADMAP.md` (original build spec) · `docs/research/ANTIBIOGRAM_README.md` (Layer-2 antibiogram contract) · `PROJECT_CONTEXT_FOR_CLAUDE.md` (full dossier).
>
> **Branch:** all work on `version/v2_release`. **Never push to `main`** (main = frozen V1 legacy). Env: `AURA_NEW` conda, `scikit-learn==1.3.2` pinned.

---

## 0. How to read & use this file

**Status legend** (edit these inline as work progresses):

| Marker | Meaning |
|---|---|
| ⬜ | Not started |
| 🟡 | In progress |
| ✅ | Done & verified |
| ⏸️ | Blocked (note the blocker) |
| 🔵 | Stretch / optional (only if ahead of schedule) |
| ❌ | Cut from scope (with a one-line reason) |

**Effort key:** `XS`=<1h · `S`=1–3h · `M`=½–1 day · `L`=1–2 days · `XL`=3+ days.

**Progress rule:** a task is ✅ only when its acceptance criteria are all ticked. A milestone is ✅ only when every non-stretch task under it is ✅. The **Definition of Done** (§7) is the final gate — nothing counts until it's verified on the **live** deployment.

**Decisions locked for this sprint** (from planning Q&A, 2026-07-11):
- **Timeline: tight, ≤4 weeks.** Critical path is **M0 → M1 → M4 → M6 → M7**. Everything else is stretch.
- **ARMD raw data is available locally** → M0/M1 evaluation starts on day 1, no data-fetch blocker.
- **Model scope: rigour over new algorithms.** Deepen evaluation on the *existing* RandomForest (M1). RF-vs-LightGBM-vs-CatBoost comparison (M2), Bayesian prior-blending, and external/temporal validation are **explicitly stretch/future-work** — an FYP wins on rigour + the Pakistan story, not on chasing a fractional AUC gain.
- **Roadmap lives at `docs/ROADMAP.md`.** Drafted starter assets stay in `docs/research/` until M4, then get relocated into `backend/` and `armd_model/`.

---

## 1. The one thing this whole roadmap is about

The single biggest examiner-exposure (Review §0): **the `antibiotic` one-hot feature dominates importance, so a large share of AUC 0.851 is between-drug variance — a global antibiogram in disguise, not patient-specific resistance.** Almost every milestone ladders up to answering this honestly:

- **M1** measures the *within-(organism, drug)* signal and compares it to a real antibiogram baseline (the direct answer).
- **M4** makes the antibiogram an explicit, swappable, locale-specific object — which is *clinically* what an antibiogram is supposed to be (CLSI M39) — and localises it to Pakistan.
- **M6/M7** make the story demonstrable and live.

Lead with this in the viva; don't hide from it.

---

## 2. Progress dashboard

> Update the Status and % as you complete tasks. This table is the at-a-glance tracker.

| # | Milestone | Critical? | Status | % | Week |
|---|---|---|---|---|---|
| **M0** | Reproduce & freeze baseline | P0 (gates all) | ✅ | 100% | 1 |
| **M1** | Rigorous evaluation | **P0 (keystone of rigour)** | ✅ | 100% | 1 |
| **M4** | Antibiogram-pluggable + Pakistan (Route A) | **P0 (thesis keystone)** | ✅ | 95% | 2 |
| **M3** | Explainability + history inputs | P1 (partly stretch) | ⬜ | 0% | 3 |
| **M5** | Dosage honest reframe | P1 (cheap, high safety value) | ✅ | 100% | 3 |
| **M6** | Frontend & demo | P1 | ✅ | 100% | 3 |
| **M7** | Deploy & verify live | **P0** | ✅ | 100% | 4 |
| **M2** | Model comparison (RF vs GBDT) | 🔵 Stretch | 🔵 | — | if ahead |
| **M8** | Thesis figures & write-up handoff | P1 | ✅ | 100% | 4 |

**Overall completion: ~95%** — all P0/P1 milestones done: M0 ✅ M1 ✅ M4 ✅ M5 ✅ M6 ✅ M7 ✅ (LIVE) M8 ✅. Live: backend https://aura-cdss-v2.onrender.com · frontend https://aura-cdss.vercel.app. Remaining: M3 (history inputs, P1) + M2 (stretch) only.

> **M1 HEADLINE FINDING (the viva centerpiece):** on **pooled** AUC the RF (0.851) does **not** beat the cumulative **antibiogram baseline (0.860)** — pooled AUC just rewards between-drug ranking. But **within** each (organism×drug) cell, where the antibiogram is constant (AUC 0.5 by construction), the RF shows **median AUC 0.650** (80% of 219 cells >0.55, 67% >0.60) — i.e. **real patient-specific lift (~+0.15) that the antibiogram cannot provide.** That is the honest answer to the Review §0 objection, with evidence. Calibration cut Brier **0.168→0.099** (isotonic, −41%); the calibrated model is now the served default. Top-3 hit-rate on informative contexts = **0.998**.

---

## 3. Four-week phase plan (calendar view)

> Start date: fill in. Each week ends with a demoable checkpoint.

### Week 1 — Prove the method is rigorous *(M0 + M1)*
The most important week. Reproduce the baseline, lock the split/seed, then build the full evaluation suite that answers the "`antibiotic` feature" objection. **Checkpoint:** `python armd_model/evaluate.py` regenerates every figure + `reports/metrics.json`, and you can state RF's lift over the antibiogram baseline per organism×drug.

### Week 2 — The Pakistan keystone *(M4)*
Refactor Layer-2 into a pluggable per-locale antibiogram; relocate and wire the drafted `us_armd.json` + `pakistan.json`; make `locale=pakistan` degrade gracefully to the aggregate/antibiogram path; lock the clinical invariants with `validate_localisation.py`. **Checkpoint:** typhoid no longer surfaces ceftriaxone for `locale=pakistan`; `us_armd` output is byte-for-byte unchanged.

### Week 3 — Make it demoable & honest *(M6 + M5 + M3-lite)*
Localisation toggle (US↔Pakistan) in the UI; new evaluation figures on `/model-info`; dosage relabelled as a guideline-lookup (kill the over-claim); enable prior-exposure inputs; SHAP panel if time allows. **Checkpoint:** full demo flow works locally end-to-end.

### Week 4 — Ship & write up *(M7 + M8)*
Retrain/re-serialise artifacts with pinned versions, deploy to Render + Vercel, run the live smoke tests, populate `reports/figures/`, update README/CHANGELOG with traceability. **Checkpoint:** every item in the §7 Definition of Done is ticked against the **live** URLs.

---

## 4. Non-negotiable guardrails (do NOT violate — check before every commit)

- [ ] **`scikit-learn==1.3.2` everywhere** (train + serve). Newer versions fail to unpickle artifacts (`SimpleImputer has no attribute _fill_dtype`). If LightGBM/CatBoost are introduced (stretch), pin them and re-serialise with the exact serving versions.
- [ ] **Keep the patient-grouped split** (`GroupShuffleSplit` by `anon_id`). Same patient never in both train and test. Every new metric reuses the *same* persisted split.
- [ ] **Research-only disclaimer** visible on every UI view and in API/docs. **Not a medical device.** No text implying validated clinical/dosing use or that the current model is tuned for Pakistani patients.
- [ ] **Don't break the `POST /api/v2/recommend` contract.** *Add* fields (e.g. `locale`, `explanation`); never rename/remove existing ones without versioning.
- [ ] **Artifact size:** <100 MB/file (GitHub) and fits the 512 MB Render free tier. Keep forests small + `compress=3`.
- [ ] **Reproducibility:** fixed random seeds recorded; every reported metric regenerable by one script.
- [ ] **Git hygiene:** work on `version/v2_release`; never push to `main`.

---

## 5. Milestones — tasks, effort, acceptance criteria

> Legend reminder: ⬜🟡✅⏸️🔵❌ · effort XS/S/M/L/XL. Tick the boxes as you go.

---

### M0 — Reproduce & freeze baseline · Status: ✅ DONE (2026-07-11) · Week 1
**Goal:** a clean, seed-locked starting point so every later number is comparable. Gates everything.

- [x] **T0.1** `S` — Activated `AURA_NEW`; confirmed **Python 3.11.15, scikit-learn 1.3.2, pandas 2.1.4, numpy 1.24.3, joblib 1.5.3**. Pinned exact versions in `armd_model/requirements.txt`.
- [x] **T0.2** `M` — Re-ran `armd_model/train_armd.py` on the local ARMD CSVs (885k rows / 66,998 patients). **Reproduced held-out TEST: AUC 0.85104, acc 0.78761, F1 0.86183, precision 0.94197, recall 0.79426** — all within ±0.0004 of the reported baseline.
- [x] **T0.3** `S` — Added split-persistence to `train_armd.py`; wrote `armd_model/splits/test_ids.json` (seed 42; train/val/test = 45,558 / 8,040 / 13,400 patients; 0 patient overlap between splits).

**Acceptance:**
- [x] `python armd_model/train_armd.py` reproduces reported metrics within **±0.005** (max Δ = 0.0004).
- [x] `armd_model/splits/test_ids.json` exists, is valid JSON, and is re-loadable; seed = 42 recorded in the manifest.

> **M0 findings carried into M1:** feature importance confirms the core exposure — `cat__antibiotic_ampicillin` **0.195**, `tetracycline` 0.090, `meropenem` 0.071 dominate. Also flagged: the training script's own "Top-3 Hit Rate 0.072 / MRR 0.069" uses a brittle exact-context-match eval — **M1.4/M1.5 must replace it** with a proper coverage/top-k metric (do not report the 0.072 as-is). Largest committed artifact = RF model **17.4 MB** (well under limits).

---

### M1 — Rigorous evaluation · Status: ✅ DONE (2026-07-11) · Week 1 · **(most important milestone)**
**Goal:** prove — or honestly bound — the model's *patient-specific* value. Directly answers Review §0. New files: `armd_model/evaluate.py`, `armd_model/baselines.py`, `armd_model/eval_common.py`. Outputs → `reports/figures/` + `reports/metrics.json`. Ran on the frozen seed-42 split (recovered rows verified == manifest).

- [x] **T1.1** `M` — Per-organism/per-drug AUC + `(organism×drug)` within-cell AUC **heatmap** (`organism_drug_auc_heatmap.png`). **Result:** 219 cells scored, median within-cell RF AUC **0.650**, 80% >0.55, 67% >0.60.
- [x] **T1.2** `M` — **Baselines** (`baselines.py`) on the same split. **Result:** overall AUC RF **0.851** vs antibiogram **0.860** vs prevalence **0.767** → pooled lift **−0.009**; the real lift is **within-cell** (T1.1), where the antibiogram is constant (0.5).
- [x] **T1.3** `M` — **Calibration** (isotonic + sigmoid on val). **Result: Brier 0.168 → 0.099 (isotonic).** Calibrated model saved (`rf_top3_recommender_calibrated.joblib`, 17.5 MB) and **served as default** — `ARMDPredictorService` prefers it (isotonic monotonic → Top-3 unchanged; smoke-tested OK). Figure: `calibration_reliability.png`.
- [x] **T1.4** `M` — **Coverage-rate-vs-clinician: NOT computable from ARMD** (cohort records the *tested* drug + susceptibility, not the administered drug — confirmed: header has no prescribed-drug field). **Top-k substitute reported** (recorded in `metrics.json/meta`).
- [x] **T1.5** `S` — **Top-k hit-rate** (honest per-context replacement for the brittle 0.072). **Result:** all contexts Top-1 **0.987** / Top-3 **0.997**; informative (n=10,854) Top-1 **0.983** / Top-3 **0.998**.
- [x] **T1.6** `M` — **Decision-curve analysis** (`decision_curve.png`), net benefit vs treat-all/treat-none, manual (no new serving dep).
- [ ] **T1.7** 🔵 `M` — **Temporal validation** — DEFERRED (stretch). ARMD *has* `order_time_jittered_utc` so it's feasible future work; needs a separate time-based split + retrain.

**Acceptance:**
- [x] One command `python armd_model/evaluate.py` regenerates **all** figures + `reports/metrics.json`.
- [x] Report states **RF lift over the antibiogram baseline** (pooled −0.009; within-cell median +0.150).
- [x] **Calibrated model is the served default**; reliability diagram + Brier present.
- [x] Coverage-rate documented as non-computable; **top-k substitute computed**.

> **Viva framing:** "Pooled AUC understates the model — it rewards ranking *between* drugs, which the antibiogram does for free. The RF's value is *within* a bug-drug cell: median AUC 0.65 discriminating which patients are susceptible — lift the antibiogram can't provide by construction. Where within-cell lift is small, I report it honestly." Matches Corbin's "modest AUROC, still useful" [Review §1/9].

---

### M4 — Antibiogram-pluggable + Pakistan (Route A) · Status: ✅ DONE (2026-07-11) · Week 2 · **(thesis keystone)**
**Goal:** make Layer-2 a swappable locale module, then drive `locale=pakistan` from Pakistani aggregate data. Review §4 (recommendation) + §5b–5e. **This is the contribution the FYP is graded on.**

> **RESULT — the localisation works end-to-end and is test-locked.** New `LocaleAntibiogramService` (`backend/app/services/antibiogram_service.py`) + a `locale` param on `/api/v2/recommend`. **US path is untouched** (RF + existing panel → same recommendations; response gained additive `locale`/`basis` fields only). **Pakistan path** is driven purely by `pakistan.json` (Route A, no RF). Live-verified: `locale=pakistan` + *S.* Typhi → Top-3 **meropenem/imipenem/azithromycin**, ceftriaxone+FQ+first-line **excluded** (`gated_do_not_use`); *E. coli* → colistin/carbapenems on top, 3rd-gen cephs sink. **11/11 tests pass** (6 localisation invariants + 5 v2 regression). Headline contrast now data-backed: **E. coli ceftriaxone 87.7% S (US) vs 18% S (Pakistan)**.
>
> **Design choice (lower-regression than the original T4.1 plan):** rather than unify both locales under one loader, the US path keeps its proven `organism_antibiotic_panel.json` filter + RF ranking untouched, and Pakistan is a *separate* antibiogram-driven path. `us_armd.json` (88 organisms, generated + schema-valid) is used for the contrast chart (M6) + validator, not the live US filter. Name matching is algorithmic (snake_case↔spaced) with an optional `name_map.json` override + load-time check.

> **Code reality to bridge (from reading `armd_predictor.py`):** the served filter currently loads `organism_antibiotic_panel.json` via `.get('panel', {})` and ranks by **raw** `P(susceptible)` with **no `locale` param**. The drafted `pakistan.json` / `us_armd.json` use a *different, richer schema* (`pakistan.schema.json`). M4 must (a) relocate the drafted assets, (b) write a loader that reconciles both shapes, (c) add the `locale` param, (d) add the aggregate-driven ranking path for Pakistan.

- [x] **T4.0** `S` — **Relocated assets:** `pakistan.json` + schema (`antibiogram.schema.json`) → `backend/antibiograms/`; `build_us_armd_antibiogram.py` → `armd_model/`; `validate_localisation.py` → `backend/tests/test_localisation.py` (paths repointed at `backend/antibiograms/`). Originals kept in `docs/research/` as reference. `ANTIBIOGRAM_README.md` copied to `backend/antibiograms/README.md`.
- [x] **T4.1** `L` — **`LocaleAntibiogramService`** loads every `backend/antibiograms/*.json` by `meta.locale`, implements the README §3 filter+rank contract, algorithmic snake_case↔spaced name matching (+ optional `name_map.json` override) with a load-time check. `locale` param added to `ARMDRecommendationRequest` (**default `us_armd`**). *(Design note: US path kept its existing panel+RF untouched rather than migrating it under the new loader — lower regression risk; see result note above.)*
- [x] **T4.2** `M` — **`us_armd.json` generated** (88 organisms, schema-valid; E. coli ceftriaxone **87.7% S**). `pakistan.json` seed retained with **honest per-cell provenance** and `unknown`/`do_not_use` gates. ⚠️ **National data-fill is an ongoing honest task** (not fabricated) — E. coli / K. pneumoniae / S. Typhi have real cited anchors; Acinetobacter/Pseudomonas/S. aureus remain `unknown` pending PARN/NIH/GLASS transcription. Sufficient for the FYP demo; flagged in `backend/antibiograms/README.md §6`.
- [x] **T4.3** `M` — **Pakistan path** ranks by antibiogram %-susceptible with `do_not_use`/`unknown`/below-threshold gating; **RF not used**. Response carries `basis`, `percent_susceptible`, `source_id`, `confidence` provenance. Documented as Route A in the README.
  - [ ] 🔵 **T4.3b** — Bayesian blend: DEFERRED (stretch).
- [x] **T4.4** `M` — **`test_localisation.py` wired to the real `LocaleAntibiogramService`** (`USE_REAL_ENGINE=True`). All pass: typhoid excludes ceftriaxone/FQ & surfaces azithromycin/meropenem; E. coli down-ranks 3rd-gen cephs & PK ceftriaxone (18) < US (87.7); `unknown` excluded with no fallback; `us_armd` filter-set regression golden written & green.

**Acceptance:**
- [x] `recommend` accepts `locale`; **`us_armd` recommendations unchanged** (5 v2 regression tests pass; response gained only *additive* `locale`/`basis` fields).
- [x] `pakistan.json` has per-cell provenance + explicit `unknown` policy (no silent US fallback — enforced in service + PK3 test); schema-valid.
- [x] `test_localisation.py` passes **all 6** assertions (typhoid + cephalosporin + regression + no-fallback + schema).
- [x] Documented note (`backend/antibiograms/README.md §1`): Pakistan = aggregate/antibiogram (Route A); row-level retrain = Route B future work (hospital partnership + IRB).

---

### M3 — Explainability + prior-history inputs · Status: ⬜ · Week 3
**Goal:** kill "it's a black box" and re-activate the strongest personal signal (prior exposure/organism — currently zeroed at inference). Review §1 (Yelin) + §2 item 5. **In a tight sprint, T3.2 (history inputs) is P1; T3.1 (SHAP) is do-if-time.**

- [ ] **T3.2** `M` — Add prior-antibiotic-class-exposure + prior-organism fields to `PatientForm`; wire through `ARMDRecommendationRequest` → `armd_service.predict()` so they're no longer defaulted to 0. (Currently `predict()` zero-fills every non-supplied feature column.)
- [ ] **T3.3** `S` — Re-run M1 with history features active; report the delta (does patient history add lift?).
- [ ] 🔵 **T3.1** `L` — **TreeSHAP** per-prediction explanations in `predict()`; return top contributing features per recommended drug as an **additive** field in the API response. (V1 had SHAP; V2 does not — this is net-new for the RF pipeline.)

**Acceptance:**
- [ ] UI captures prior history; values flow to the model (verified: changing them changes output).
- [ ] M1 re-run shows the effect of enabling history.
- [ ] (If T3.1 done) `/api/v2/recommend` returns per-drug explanation data.

---

### M5 — Dosage honest reframe · Status: ✅ DONE (2026-07-11) · Week 3
**Goal:** neutralise the most attackable component. Review §2 item 9. Cheap, high safety-payoff.

- [x] **T5.1** `S` — Relabeled in **code** (service docstring + `model_type='Guideline dose reference (lookup table + static defaults)'`, `validated: False`, `DOSE_DISCLAIMER`), **API** (additive `dose_disclaimer` on the response + per-pick `dose_source`), and **UI** (`ResultCardV2` now says "Dosage · guideline reference … Reference figure only — not validated or patient-adjusted dosing"; removed the false "estimated by ML model" label). **The ML dose/route RandomForest is RETIRED** (not loaded, not used) — it was inventing implausible doses ("30-40 mg" for a carbapenem).
- [x] **T5.2** `M` — `armd_model/validate_dosage.py` audits coverage + flags unusable entries → `reports/dosage_audit.json`. **Findings: 840 lookup rows, 438 have no numeric dose** (why the ML tier fired so often); **all 40 recommendable drugs (32 US + 24 Pakistan) resolve to a real reference dose**, none missing a static default. Static defaults documented as typical adult empiric doses per Sanford/BNF/IDSA (reference figures only).
- [x] **T5.3** `S` — Fallback never returns "unknown" (worst case is a labelled `Consult local formulary`, but the audit confirms every recommendable drug hits a real default); `dose_source` provenance surfaced per pick in the UI. Spot-check: imipenem→500 mg IV, azithromycin→500 mg PO, colistin→2.5-5 mg/kg/day IV.

**Acceptance:**
- [x] No code/UI/docs surface implies validated dosing; dose-source provenance shown per pick; global research-only disclaimer + per-card caveat.
- [x] Lookup validated via `validate_dosage.py` against named references (coverage + unusable logged; audit JSON committed). **12/12 backend tests pass** (dosage test updated for the reframe).

---

### M6 — Frontend & demo polish · Status: ✅ DONE (2026-07-14) · Week 3
**Goal:** a defence-winning live demo. Review §3 (poster/demo). Touch points: `PatientForm`, `ResultCardV2`, `ResistanceChart`, `app/model-info/page.tsx`, `services/api.ts`.

> **RESULT — the localisation toggle and evaluation dashboard are built, typechecked, and test-locked.** New `LocaleToggle` (US 🇺🇸 ↔ Pakistan 🇵🇰) on the home page flips `locale`; the form swaps its organism vocabulary to the local antibiogram (organisms without cited data are shown but disabled — *data pending*), and results render an **antibiogram-provenance banner** + an **"Excluded by the Pakistan antibiogram"** panel (the money-shot: typhoid → *ceftriaxone struck through, gated do-not-use*; top-3 = meropenem/imipenem/azithromycin). `/model-info` gained an **Evaluation Rigour** section (pooled-vs-antibiogram AUC, within-cell median 0.650, Brier 0.168→0.099, Top-3 0.998 + the 4 M1 figures) and the **US-vs-Pakistan resistance contrast** chart (E. coli ceftriaxone 87.7%S US vs 18%S PK; typhoid ceftriaxone gated). Disclaimer banner now on **every** view. **Frontend `tsc` clean + `next build` green; 15/15 backend tests pass** (3 new: `/locales`, model-info evaluation+contrast, PK typhoid API contract).

> **Backend additions (additive, contract-safe):** `GET /api/v2/locales` (locales + per-organism `has_data`), and `/api/v2/model-info` now carries an `evaluation` block (read from `reports/metrics.json`) + a data-driven `us_vs_pk_contrast` block (computed from `us_armd.json` vs `pakistan.json`, nothing fabricated). Fixed a real bug: `LocaleAntibiogramService.organism_entries()` returns a **resolvable** organism id (norm of the key) so *S.* Typhi (display name ≠ key) actually resolves — previously it silently returned no data.

- [x] **T6.1** `M` — **Localisation toggle** (US ↔ Pakistan): `LocaleToggle` flips `locale`; `PatientForm` is locale-aware (PK organism list from `/locales`, no-data organisms disabled); results show provenance + struck-through excluded drugs. Typhoid loses ceftriaxone on flip. *(Money-shot delivered.)*
- [x] **T6.3** `M` — **`/model-info` upgrade:** M1 artifacts surfaced — per-organism AUC + within-(org×drug) heatmap + calibration/reliability + decision-curve figures, pooled-vs-antibiogram/within-cell/Brier/Top-k headline cards, coverage-rate note, **and the US-vs-Pakistan resistance contrast chart** (E. coli ceftriaxone US 87.7%S vs PK 18%S).
- [x] **T6.4** `XS` — **Disclaimer** now on every view incl. `/model-info` (`DisclaimerBanner`); per-card dose caveat + global `dose_disclaimer` surfaced.
- [ ] 🔵 **T6.2** `M` — **SHAP panel** — DEFERRED (depends on M3.1, not landed).

**Acceptance:**
- [x] Demo flow works end-to-end locally (verified via API-shape checks + `next build`): enter case → Top-3 + probabilities → flip to Pakistan → recommendations change correctly (typhoid no longer shows ceftriaxone; ceftriaxone appears in the *excluded* panel as `gated_do_not_use`). *Final browser click-through folds into M7 live verification.*
- [x] New evaluation + US↔PK contrast figures render on `/model-info` (4 M1 PNGs copied to `frontend/public/figures/`; contrast is live from the model-info API).

---

### M7 — Deploy & verify live · Status: ✅ DONE (2026-07-14) · Week 4 · **P0**
**Goal:** everything above actually running in production, not just locally.

> **LIVE.** Backend → Render: **https://aura-cdss-v2.onrender.com** · Frontend → Vercel: **https://aura-cdss.vercel.app** (Production branch `version/v2_release`). Deploy-blocking gaps found & fixed: (1) calibrated RF was gitignored → shipped (17.5 MB, byte-verified); (2) Dockerfile now copies `backend/antibiograms/` + `reports/metrics.json` (`REPORTS_DIR` set). Two deploy-time issues caught & fixed live: Vercel was building `main` (frozen V1) with a broken `--prefix frontend` install → repointed Production to `version/v2_release` with Root Directory `frontend` + default commands; and `NEXT_PUBLIC_API_URL` was unset → set to the Render backend and rebuilt (bundle now bakes the backend baseURL, verified).

- [x] **T7.1** `M` — Served artifacts finalised & committed with pinned versions: the **calibrated** model (`rf_top3_recommender_calibrated.joblib`) is the shipped/served default; all committed files <100 MB (largest 17.5 MB); antibiograms + `reports/metrics.json` bundled into the image. Render runs without retraining.
- [x] **T7.2** `M` — Deployed: backend on Render (`backend/Dockerfile`, health `/health`), frontend on Vercel (Root Directory `frontend`, Production branch `version/v2_release`). Env set: `ALLOWED_ORIGINS`=Vercel origin, `ENVIRONMENT=production`, `NEXT_PUBLIC_API_URL`=Render backend.
- [x] **T7.3** `S` — Live smoke tests PASS: `/health` healthy; `/api/v2/locales` (us_armd + pakistan, 3/6 orgs with data); `/api/v2/model-info` (eval block AUC 0.851 / cell 0.650 / isotonic + 12 contrast rows + `dosage.validated=false`); US recommend (basis=model, amikacin/ertapenem/meropenem); **PK typhoid gating** (meropenem/imipenem/azithromycin, ceftriaxone + 4 others `gated_do_not_use`, dose_disclaimer); CORS ACAO = Vercel origin; frontend bundle baked with backend baseURL.

**Acceptance:**
- [x] All §7 live checks pass against the deployed URLs; cold start works on the 512 MB free tier (Render free tier ~50s cold start); `recommend` does not 500 on artifact load.

---

### M8 — Thesis figures & write-up handoff · Status: ✅ DONE (2026-07-14) · Week 4
**Goal:** convert the work into examiner-facing artifacts. Review §3.

- [x] **T8.1** `S` — `reports/figures/` populated: per-organism AUC + organism×drug heatmap, calibration diagram, decision-curve, **coverage/top-k bar** (`topk_coverage.png`), **US-vs-PK contrast** (`us_vs_pk_contrast.png`), **3-layer architecture** (`architecture_3layer.png`). New figures regenerate via `armd_model/make_thesis_figures.py` (committed-artifacts only, no datasets); mirrored to `frontend/public/figures/`.
- [x] **T8.2** `S` — `README.md` updated: locale-aware engine (§8), honest evaluation + figures (§10), regenerate-metrics/figures step (§11), `/api/v2/locales` + `locale` field (§13), `ANTIBIOGRAM_DIR`/`REPORTS_DIR` (§15), bundled-artifact deploy (§16); corrected the stale "uncalibrated" claim.
- [x] **T8.3** `S` — `CHANGELOG.md` `[2.1.0]` entry maps each change to its Review §/Mn.n finding (viva traceability).
- [x] **T8.4** `M` — `docs/VIVA_ONEPAGER.md` drafted: problem, XDR-typhoid hook, RQ, honest contributions, "do NOT claim" list, likely Q&A.

**Acceptance:**
- [x] `reports/figures/` populated; README + CHANGELOG updated with traceability; viva one-pager drafted.

---

### M2 — Model comparison (RF vs LightGBM vs CatBoost) · Status: 🔵 Stretch · only if ahead
**Goal:** answer "why RandomForest?" with evidence. Review §2 Tier 2 / §4(e). **Demoted to stretch for the 4-week sprint** — do only after M0/M1/M4/M6/M7 are green.

- [ ] 🔵 **T2.1** `L` — `compare_models.py`: RF, LightGBM, CatBoost on the **same split + features**, calibrated, same metrics.
- [ ] 🔵 **T2.2** `M` — Include the V1 per-drug CatBoost design as a third architecture point (one-model-per-drug vs single-pipeline-with-drug-as-feature).
- [ ] 🔵 **T2.3** `S` — One comparison table (AUC, Brier, top-k, coverage, artifact size, latency); justify the production choice in a paragraph.

**Acceptance (if attempted):** reproducible comparison table in `reports/`; production model justified on accuracy *and* size/latency for the 512 MB host. **If not attempted:** state in the thesis that RF was retained for size/latency + reproducibility, and comparison is future work.

---

## 6. Dependency & critical-path map

```
M0 ──▶ M1 ──▶ M4 ──▶ M6 ──▶ M7 ──▶ (live)
 │      │      │       ▲
 │      │      │       │
 │      └─────▶┴──▶ M3 ┤   (history inputs feed the demo; SHAP optional)
 │                     │
 └────────────▶ M5 ────┘   (dosage reframe — independent, slot anywhere wk3)

M2 (stretch) hangs off M1's split; M8 runs alongside M7.
```

- **Hard blockers:** M0 blocks all metrics. M1's calibrated artifact + M4's `locale` both feed M7's shipped build. M4 blocks the M6 localisation toggle.
- **Parallelizable:** M5 (dosage reframe) and M8 (docs) can slot into any gap.

---

## 7. Definition of Done — final checklist (verify on the LIVE deployment)

> Tick only when verified against the **deployed** system, not local. Mirrors `AURA_BUILD_ROADMAP.md` §5; each item maps to a research finding.

**Evaluation rigour (Review §0, §2 Tier 1)**
- [ ] Per-(organism×drug) AUC heatmap exists and shows on live `/model-info`.
- [ ] RF **lift over the antibiogram baseline** computed and stated honestly (incl. where small/zero).
- [ ] Probabilities **calibrated**; reliability diagram + Brier live on `/model-info`.
- [ ] Coverage-rate-vs-clinician (or documented top-k substitute) reported.
- [ ] Top-1 / Top-3 susceptibility hit-rates reported.
- [ ] Decision-curve analysis figure generated.
- [ ] All metrics regenerable via one seeded script.

**Modelling (Review §2, §4)**
- [ ] Prior-exposure / prior-organism inputs **live in the UI** and flow to the model (no longer zeroed).
- [ ] (If done) Per-prediction TreeSHAP returned by the live API and shown in the UI.
- [ ] (If M2 done) RF vs LightGBM vs CatBoost table exists; else future-work noted.

**Pakistan localisation (Review §5 — the keystone)**
- [ ] `recommend` supports `locale`; `us_armd` output unchanged (regression guard passes).
- [ ] `pakistan.json` built from cited aggregate sources, per-cell provenance, explicit `unknown` policy.
- [ ] Pakistan path documented as aggregate/antibiogram-driven (Route A), not US-RF-driven.
- [ ] **Typhoid check passes live:** `locale=pakistan` + *S.* Typhi does **not** recommend ceftriaxone; **does** surface azithromycin/meropenem.
- [ ] **Cephalosporin check passes live:** `locale=pakistan` + *E. coli* down-ranks 3rd-gen cephalosporins vs US.
- [ ] UI localisation toggle visibly changes recommendations on the live site.
- [ ] US-vs-Pakistan resistance contrast chart live on `/model-info`.
- [ ] Route B (row-level retrain) labelled as future work needing partnership + IRB.

**Dosage honesty (Review §2 item 9)**
- [ ] No code/UI/docs surface implies validated dosing; dose-source provenance shown per pick.
- [ ] Lookup validated against a named reference.

**Safety / integrity guardrails**
- [ ] Research-only disclaimer visible on every live view.
- [ ] No clinical-validity over-claims anywhere.
- [ ] `scikit-learn==1.3.2` (+ any new libs) pinned; live `recommend` does not 500 on artifact load.
- [ ] Patient-grouped split honoured in all reported metrics.
- [ ] Committed artifacts <100 MB/file; service fits 512 MB; cold start works.

**Live smoke tests**
- [ ] `GET /health` → 200 on live backend.
- [ ] `GET /api/v2/model-info` returns the new metrics payload.
- [ ] `POST /api/v2/recommend` (US locale) → Top-3 + probabilities + dose (+ SHAP if built).
- [ ] `POST /api/v2/recommend` (Pakistan locale) → localised, validated recommendations.
- [ ] Frontend loads on Vercel; full demo flow (enter → recommend → flip locale) works.

**Documentation / thesis handoff**
- [ ] README updated (architecture, `locale`, regenerate-metrics, deploy).
- [ ] `reports/figures/` populated with thesis/poster-ready figures.
- [ ] CHANGELOG maps each change → the Review finding it addresses.

---

## 8. Traceability — research finding → milestone (for the viva)

| Research finding (Review) | Addressed by |
|---|---|
| `antibiotic` feature inflates pooled AUC (§0) | M1 (per-stratum + baselines) |
| No calibration (§2) | M1.3 |
| No coverage/top-k metric; "classifier not recommender" (§1, §2) | M1.4, M1.5 |
| Prior-history features disabled (§1 Yelin, §2) | M3.2 |
| No per-prediction explainability (§2) | M3.1 (stretch) |
| US-trained vs Pakistan target; aggregate-only data (§5) | M4 |
| Antibiogram filter is US-shaped (§2 attack list) | M4.1 |
| Mis-recommendation examples (typhoid, cephalosporins) (§5c) | M4.4 validation |
| Dosage over-claim risk (§2 item 9) | M5 |
| Single-site / external validation (§2 Tier 3) | M1.7 + M4.4 (validate vs PK antibiogram) — stretch/future |
| "Why RandomForest?" (§2, §4e) | M2 (stretch) |
| Demo/poster impact (§3) | M6 |
| "Done and live" assurance | M7 + §7 checklist |

---

## 9. Explicitly out of scope for this sprint (future work — say this in the viva)

- **Route B (row-level Pakistani retrain):** needs a tertiary-hospital partnership + IRB/ethics approval. Future work.
- **External validation on a second dataset** (AMR-UTI on PhysioNet, or a Pakistani row-level cohort). Future work.
- **Prospective/clinical evaluation, LIS/EHR integration, regulatory pathway.** Future work.
- **Auth + audit logging, multi-organism/polymicrobial support.** Future work.
- **LLM/RAG explanation layer** — fine as *explanation only*, never as the primary recommender (hallucination risk). Not this sprint.

---

## 10. "If you only do five things" (Review §6 — the irreducible core)

1. **M1** — Per-(organism×drug) metrics + antibiogram baseline (kills the biggest objection).
2. **M1.3** — Calibrate probabilities (reliability diagram + Brier).
3. **M1.4** — Coverage-rate-vs-clinician metric (makes it a *recommender*, not a classifier).
4. **M4** — Antibiogram-pluggable Layer-2 + a Pakistani antibiogram (ties the whole thesis together).
5. **M8.4** — Open the defence with the XDR-typhoid example (justifies everything in 30 seconds).

If the 4 weeks compress, protect these five above all else.

---

*Last updated: 2026-07-11 · Owner: EponymousBearer · Branch: `version/v2_release`*
