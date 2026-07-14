# -*- coding: utf-8 -*-
"""
make_thesis_figures.py  (M8 — examiner-facing figures)
======================================================
Regenerates the poster/thesis figures that DON'T need the raw cohort — they read
only committed artifacts (reports/metrics.json + backend/antibiograms/*.json), so
this runs anywhere without the datasets:

    python armd_model/make_thesis_figures.py

Produces (into reports/figures/, then mirrored to frontend/public/figures/):
  topk_coverage.png       Top-1 / Top-3 susceptibility hit-rate (T1.5 substitute for coverage-rate).
  us_vs_pk_contrast.png   US vs Pakistan %-susceptible for the keystone divergence cells (M4/M6).
  architecture_3layer.png The 3-layer recommendation engine (RF score -> antibiogram filter -> dose).

The four evaluation figures (per_organism_auc, organism_drug_auc_heatmap,
calibration_reliability, decision_curve) come from armd_model/evaluate.py, which
needs the cohort. Run both to refresh every figure.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports" / "figures"
PUBLIC_FIG_DIR = ROOT / "frontend" / "public" / "figures"
METRICS = ROOT / "reports" / "metrics.json"

# Reuse the SAME service + contrast pairs the live API serves, so figures match /model-info.
sys.path.insert(0, str(ROOT / "backend"))
from app.services.antibiogram_service import LocaleAntibiogramService  # noqa: E402

_CONTRAST_PAIRS = [
    ("escherichia coli", "ceftriaxone"),
    ("escherichia coli", "ciprofloxacin"),
    ("escherichia coli", "ampicillin"),
    ("escherichia coli", "trimethoprim sulfamethoxazole"),
    ("escherichia coli", "meropenem"),
    ("escherichia coli", "nitrofurantoin"),
    ("klebsiella pneumoniae", "ciprofloxacin"),
    ("klebsiella pneumoniae", "gentamicin"),
    ("salmonella typhi", "ceftriaxone"),
    ("salmonella typhi", "ciprofloxacin"),
    ("salmonella typhi", "azithromycin"),
]
_US_ORG_ALIAS = {"salmonella typhi": "salmonella enterica"}

BLUE = "#2563eb"
AMBER = "#f59e0b"
RED = "#dc2626"
GREEN = "#16a34a"
SLATE = "#334155"


def _titlecase(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split())


def save(fig, name: str):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_FIG_DIR.mkdir(parents=True, exist_ok=True)
    for d in (FIG_DIR, PUBLIC_FIG_DIR):
        fig.savefig(d / name, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}")


# ---------------------------------------------------------------------------
def fig_topk_coverage(metrics: dict):
    tk = metrics["top_k"]
    labels = ["Top-1\n(all contexts)", "Top-3\n(all contexts)",
              "Top-1\n(informative)", "Top-3\n(informative)"]
    vals = [tk["top1_hit_rate_all"], tk["top3_hit_rate_all"],
            tk["top1_hit_rate_informative"], tk["top3_hit_rate_informative"]]
    colors = [AMBER, BLUE, AMBER, BLUE]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.bar(labels, vals, color=colors, width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v*100:.1f}%",
                ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylim(0.90, 1.005)
    ax.set_ylabel("Susceptibility hit-rate")
    ax.set_title("Top-k susceptibility hit-rate — does the top-ranked drug actually work?\n"
                 f"(coverage-rate substitute, T1.4/T1.5;  informative n={tk['n_informative_contexts']:,})",
                 fontsize=11)
    ax.axhline(1.0, ls="--", c="gray", lw=1)
    ax.grid(axis="y", alpha=0.25)
    fig.text(0.5, -0.02,
             "'Informative' = contexts with >=1 resistant AND >=1 susceptible tested drug — "
             "the only cases where ranking can be wrong.",
             ha="center", fontsize=8.5, color=SLATE)
    save(fig, "topk_coverage.png")


def fig_us_vs_pk(svc: LocaleAntibiogramService):
    rows = []
    for organism, drug in _CONTRAST_PAIRS:
        pk = svc.get_cell("pakistan", organism, drug) or {}
        pk_status = pk.get("status")
        pk_pct = pk.get("percent_susceptible")
        gated = pk_status == "do_not_use"
        if pk_pct is None and not gated:
            continue
        us_org = _US_ORG_ALIAS.get(organism, organism)
        us = svc.get_cell("us_armd", us_org, drug) or {}
        us_pct = us.get("percent_susceptible")
        drug_label = "TMP-SMX" if drug == "trimethoprim sulfamethoxazole" else _titlecase(drug)
        rows.append({
            "label": f"{_shorten_org(organism)}\n{drug_label}",
            "us": None if us_pct is None else float(us_pct),
            "pk": 0.0 if gated else float(pk_pct),
            "gated": gated,
        })
    # gated + biggest divergence first
    rows.sort(key=lambda r: (not r["gated"],
                             -(abs((r["us"] or 0) - r["pk"]))))
    labels = [r["label"] for r in rows]
    us_vals = [r["us"] if r["us"] is not None else 0 for r in rows]
    pk_vals = [r["pk"] for r in rows]
    import numpy as np
    x = np.arange(len(rows))
    w = 0.38
    fig, ax = plt.subplots(figsize=(12, 6))
    b1 = ax.bar(x - w / 2, us_vals, w, label="US (ARMD / Stanford)", color=BLUE)
    b2 = ax.bar(x + w / 2, pk_vals, w, label="Pakistan (provisional seed)", color=AMBER)
    for i, r in enumerate(rows):
        if r["us"] is None:
            ax.text(x[i] - w / 2, 2, "n/a", ha="center", va="bottom", fontsize=8, color="gray")
        if r["gated"]:
            ax.text(x[i] + w / 2, 3, "GATED\n(do-not-use)", ha="center", va="bottom",
                    fontsize=7.5, color=RED, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=15, ha="center")
    ax.set_ylabel("% susceptible")
    ax.set_ylim(0, 105)
    ax.set_title("Why locale matters: US vs Pakistan empiric susceptibility for the same bug-drug pairs\n"
                 "Ceftriaxone — US first-line for typhoid — is gated in Pakistan (XDR S. Typhi outbreak)",
                 fontsize=11)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    fig.text(0.5, -0.03,
             "US = ARMD proof-of-method antibiogram. Pakistan = provisional single-centre seed — "
             "illustrative, NOT a validated national comparison.",
             ha="center", fontsize=8.5, color=SLATE)
    save(fig, "us_vs_pk_contrast.png")


def _shorten_org(o: str) -> str:
    parts = o.split()
    if len(parts) >= 2:
        return f"{parts[0][0].upper()}. {parts[1]}"
    return _titlecase(o)


def fig_architecture():
    fig, ax = plt.subplots(figsize=(11, 7.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    def box(x, y, w, h, title, body, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.15",
                                    linewidth=1.6, edgecolor=color, facecolor=color + "18"))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="top",
                fontsize=11, fontweight="bold", color=color)
        ax.text(x + w / 2, y + h - 0.78, body, ha="center", va="top",
                fontsize=8.6, color=SLATE)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=18, lw=1.6, color=SLATE))

    # Input
    box(0.3, 8.2, 9.4, 1.4, "Request:  patient context + locale",
        "organism, culture site, age, sex, ward, WBC / creatinine / lactate / procalcitonin,  locale = us_armd | pakistan",
        SLATE)
    arrow(5, 8.2, 5, 7.55)

    # Router
    box(2.6, 6.1, 4.8, 1.35, "Locale router",
        "locale=us_armd -> Layers 1-3 (model)\nlocale=pakistan -> Route A (antibiogram-only)",
        "#7c3aed")
    arrow(3.4, 6.1, 2.4, 5.15)   # to model path
    arrow(6.6, 6.1, 7.6, 5.15)   # to route A

    # ---- Model path (US) ----
    box(0.3, 3.7, 4.3, 1.4, "Layer 1 — RF scorer",
        "calibrated RandomForest scores all 32\ncandidate antibiotics  (isotonic, Brier 0.099)",
        BLUE)
    arrow(2.45, 3.7, 2.45, 3.15)
    box(0.3, 1.7, 4.3, 1.4, "Layer 2 — Antibiogram filter",
        "drop drugs the lab never tests for\nthis organism  (CLSI M39, >=30 isolates)",
        GREEN)
    arrow(2.45, 1.7, 2.45, 1.15)

    # ---- Route A (Pakistan) ----
    box(5.4, 2.7, 4.3, 2.4, "Route A — locale antibiogram",
        "rank by local %-susceptible;\nexclude tested=false / unknown /\ndo-not-use / below-threshold;\nNO US fallback (honest gaps)",
        AMBER)
    arrow(7.55, 2.7, 4.65, 0.9)

    # Output
    box(0.3, 0.15, 9.4, 1.0, "Layer 3 — Top-3 + dose  (with provenance + research-only disclaimer)",
        "each pick carries basis (model | antibiogram), %-susceptible / probability, source id, and a non-validated-dosing note",
        RED)

    ax.text(5, 9.85, "AURA — 3-layer locale-aware recommendation engine",
            ha="center", fontsize=13, fontweight="bold", color="#0f172a")
    save(fig, "architecture_3layer.png")


def main():
    print("M8 — thesis figures")
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    svc = LocaleAntibiogramService()
    fig_topk_coverage(metrics)
    fig_us_vs_pk(svc)
    fig_architecture()
    print(f"Done -> {FIG_DIR}  (+ mirrored to {PUBLIC_FIG_DIR})")


if __name__ == "__main__":
    main()
