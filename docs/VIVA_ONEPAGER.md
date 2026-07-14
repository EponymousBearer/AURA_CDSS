# AURA — Viva one-pager

> **Research/educational prototype. Not a validated clinical or dosing tool. Never the sole basis for a prescribing decision.**
> One-page defence brief for the examiner. Numbers are from the frozen seed-42, patient-grouped evaluation (`reports/metrics.json`, regenerable via `armd_model/evaluate.py`).

---

## Problem statement
Empiric antibiotic therapy is chosen **before** culture susceptibility results return (24–72 h). Choose too broad and you drive resistance; too narrow and you undertreat. Clinicians lean on a **cumulative antibiogram** (population %-susceptible per organism×drug), but that is a *population* average — it ignores the individual patient's demographics, labs, ward, and history, and it is **locale-specific**: the right empiric drug in the US can be the wrong one in Pakistan.

## The hook — XDR typhoid
Since 2016 Pakistan has an ongoing **extensively-drug-resistant (XDR) *Salmonella* Typhi** outbreak: resistant to first-line agents, fluoroquinolones, **and** third-generation cephalosporins. **Ceftriaxone — the standard empiric choice for typhoid in the US — fails in Pakistan.** A CDSS that silently reused a US-trained model would confidently recommend a drug that doesn't work. AURA's locale layer **gates** ceftriaxone for typhoid in Pakistan and surfaces azithromycin / carbapenems instead. This is the concrete demonstration that *locale must be explicit*.

## Research question
> Given a patient context and organism, can a single model **re-rank** candidate antibiotics by susceptibility **better than the population antibiogram for that individual**, and can the same system be made **locale-aware** so its recommendations remain honest outside the training region?

## What AURA actually is
A 3-layer, locale-aware recommender. **Layer 0** routes on `locale`: `us_armd` → ML path; `pakistan` → antibiogram-only *Route A* (rank by local %-susceptible, exclude untested/unknown/below-threshold/`do_not_use`, **no US fallback**). ML path: **L1** a single calibrated RandomForest (with `antibiotic` as a *feature*, so one model scores all 32 drugs) → **L2** antibiogram filter (CLSI M39, ≥30 isolates — kills clinically nonsensical picks) → **L3** rank, Top-3 + dose.

## Honest contributions (what to claim)
1. **A rigorous, seeded, patient-grouped evaluation** (no leakage: `GroupShuffleSplit` by `anon_id`) measured against the **right baseline** — the antibiogram, not just chance.
2. **The honest headline:** pooled RF AUC **0.851 < antibiogram 0.860**, but **within-(organism×drug) median AUC 0.650** — i.e. the model's value is *patient-specific re-ranking inside a cell*, where the antibiogram is constant (AUC 0.5). 80% of cells beat 0.55.
3. **Calibrated, decision-grade probabilities** — isotonic, Brier **0.168 → 0.099**, order-preserving so Top-k is unchanged. The calibrated model is the served default.
4. **Top-1/Top-3 susceptibility hit-rate 0.983 / 0.998** on informative contexts (both an S and an R drug tested) — the honest substitute for coverage-rate, which ARMD cannot support.
5. **Locale-aware serving** with a provisional Pakistan antibiogram that *gates* XDR drugs and **shows its data gaps** rather than inventing numbers.
6. **A safety-first architecture**: the ML proposes, the antibiogram disposes, provenance + disclaimers travel with every recommendation.

## Do **NOT** claim (say these before you're asked)
- ❌ "The model beats the antibiogram." → It does **not**, pooled. The win is within-cell re-ranking only.
- ❌ "The model is trained/tuned for Pakistani patients." → The **model** is US ARMD data; Pakistan is served by a **separate antibiogram**, not a retrained model.
- ❌ "AURA gives validated doses." → Dosing is a **reference reframe** with a non-validated disclaimer; no weight/renal/indication logic.
- ❌ "The Pakistan antibiogram is authoritative." → It's a **provisional single-centre/literature seed** with explicit `unknown` cells and TODO placeholders for national PARN/NIH/GLASS data.
- ❌ "It's clinically validated / ready to use." → Research prototype, **no external validation**, single US institution, decision-support only.

## Likely questions & answers
- **Q: If the antibiogram wins pooled, why use ML at all?** *Pooled AUC hides the use case. Inside one organism×drug cell the antibiogram is a single constant number (AUC 0.5); the RF's cell AUC of ~0.65 is real patient-level discrimination that a population rate cannot provide. AURA uses **both** — antibiogram as the safety filter, RF for the within-cell ordering.*
- **Q: Isn't `antibiotic`-as-a-feature just a lookup of base rates?** *That's exactly why feature importance is dominated by antibiotic identity — the model learns each drug's base susceptibility and then modulates it by organism and patient. One model generalises across drugs and can score drug×organism interactions a per-drug model can't share.*
- **Q: How do you know there's no leakage?** *Patient-grouped split by `anon_id`, asserted zero-overlap across train/val/test; a fixed seed; and the eval script asserts the AUC hasn't drifted from the frozen baseline.*
- **Q: Why RandomForest, not XGBoost/CatBoost?** *Retained for reproducibility and to fit the 512 MB free-tier host after `compress=3` (17.5 MB). A formal RF-vs-LightGBM-vs-CatBoost comparison on the same split is scoped as future work (roadmap M2).*
- **Q: Coverage-rate vs clinician?** *Not computable from ARMD — it records the drug **tested**, not the drug **administered** (no prescribed-drug field). Top-k susceptibility hit-rate is the documented substitute.*
- **Q: Are the probabilities meaningful?** *Yes after isotonic calibration (Brier 0.099). Because isotonic is monotonic it preserves ranking, so calibration improves the *values* without disturbing Top-k.*
- **Q: What breaks if you deploy this in a Pakistani hospital tomorrow?** *The model is US-trained; only the antibiogram is local, and it's a seed. It needs a real national antibiogram and prospective validation first. That honesty is the point of the locale split.*

## One-line summary
*A leakage-free, calibrated, locale-aware antibiotic recommender whose contribution is honest patient-specific re-ranking within the antibiogram — not beating it — demonstrated by gating XDR-typhoid ceftriaxone in Pakistan.*

**See also:** `README.md` (§8 engine, §10 evaluation), `docs/ROADMAP.md` (milestones), `reports/figures/` (heatmap, calibration, decision-curve, US-vs-PK contrast, architecture).
