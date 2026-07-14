"""
API routes for the Antibiotic AI CDSS.
v1: CatBoost-based (/api/v1/*)  — DISABLED, superseded by v2 (commented out below)
v2: ARMD RandomForest-based (/api/v2/*)  — ACTIVE
"""

from fastapi import APIRouter, HTTPException, status, Response, Query
from fastapi.responses import JSONResponse
import json
import logging
import os
from pathlib import Path
from uuid import uuid4
from typing import Dict

from app.schemas.request import (
    # --- V1 schemas (CatBoost) — DISABLED ---
    # AntibioticRecommendationRequest,
    # AntibioticRecommendationResponse,
    # AntibioticExplainRequest,
    ARMDRecommendationRequest,
    ARMDRecommendationResponse,
    ErrorResponse,
)
# --- V1 services (CatBoost) — DISABLED ---
# from app.services.predictor import PredictionService
# from app.services.rules import DosingRuleEngine
from app.services.armd_predictor import ARMDPredictorService
from app.services.dosage_service import DosageService, DOSE_DISCLAIMER
from app.services.clinical_catalog import ClinicalCatalogService
from app.services.antibiogram_service import LocaleAntibiogramService

logger = logging.getLogger(__name__)

# --- V1 router + services (CatBoost) — DISABLED, superseded by v2 ARMD ---
# router = APIRouter()
# prediction_service = PredictionService()
# dosing_engine = DosingRuleEngine()

# V2 services (ARMD RandomForest)
armd_service = ARMDPredictorService()
dosage_service = DosageService()
clinical_catalog_service = ClinicalCatalogService()
antibiogram_service = LocaleAntibiogramService()  # pluggable per-locale antibiograms (M4)

# ── Evaluation artifacts (M1) surfaced on /model-info (M6) ──
# reports/ lives at the repo root: backend/app/api/routes.py -> ../../../reports
_REPORTS_DIR = Path(os.getenv("REPORTS_DIR", Path(__file__).resolve().parents[3] / "reports"))


def _load_evaluation_summary() -> Dict:
    """Read reports/metrics.json (M1) into a compact block for the dashboard.

    Returns {} if the file is absent (e.g. metrics not yet generated) so the
    endpoint never 500s on a fresh checkout.
    """
    path = _REPORTS_DIR / "metrics.json"
    if not path.exists():
        return {}
    try:
        m = json.load(open(path, encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Could not read {path}: {exc}")
        return {}

    overall = m.get("overall", {})
    rf = overall.get("rf", {})
    cell = m.get("per_cell_summary", {})
    topk = m.get("top_k", {})
    calib = m.get("calibration", {})
    return {
        "seed": (m.get("meta") or {}).get("seed"),
        "n_test_rows": (m.get("meta") or {}).get("n_test_rows"),
        "n_test_patients": (m.get("meta") or {}).get("n_test_patients"),
        "pooled": {
            "rf_roc_auc": rf.get("roc_auc"),
            "antibiogram_baseline_auc": overall.get("antibiogram_baseline_auc"),
            "prevalence_baseline_auc": overall.get("prevalence_baseline_auc"),
            "rf_lift_over_antibiogram_auc": overall.get("rf_lift_over_antibiogram_auc"),
        },
        "within_cell": {
            "n_cells": cell.get("n_cells_evaluated"),
            "median_rf_cell_auc": cell.get("median_rf_cell_auc"),
            "frac_cells_auc_gt_0_55": cell.get("frac_cells_auc_gt_0_55"),
            "frac_cells_auc_gt_0_60": cell.get("frac_cells_auc_gt_0_60"),
        },
        "calibration": {
            "brier_uncalibrated": calib.get("brier_uncalibrated"),
            "brier_isotonic": calib.get("brier_isotonic"),
            "served_method": calib.get("served_method"),
        },
        "top_k": {
            "top1_informative": topk.get("top1_hit_rate_informative"),
            "top3_informative": topk.get("top3_hit_rate_informative"),
            "n_informative_contexts": topk.get("n_informative_contexts"),
        },
        "coverage_note": (m.get("meta") or {}).get("coverage_rate_vs_clinician"),
        "figures": [
            {"file": "per_organism_auc.png",
             "title": "Per-organism ROC AUC",
             "caption": "Discrimination varies by organism; pooled AUC hides this."},
            {"file": "organism_drug_auc_heatmap.png",
             "title": "Within-(organism × drug) AUC",
             "caption": "Where the antibiogram is constant (AUC 0.5), cell AUC > 0.5 is the RF's patient-specific lift."},
            {"file": "calibration_reliability.png",
             "title": "Calibration / reliability",
             "caption": "Isotonic calibration cut Brier 0.168 → 0.099; the calibrated model is served."},
            {"file": "decision_curve.png",
             "title": "Decision-curve analysis",
             "caption": "Net benefit vs treat-all / treat-none across thresholds."},
        ],
    }


# Curated organism/drug pairs for the US-vs-Pakistan contrast chart (M6, T6.3).
# The list is a hint; only pairs where BOTH locales have a usable value (or PK
# explicitly gates the drug) are emitted, so nothing is fabricated.
_CONTRAST_PAIRS = [
    ("escherichia coli", "ceftriaxone"),
    ("escherichia coli", "cefotaxime"),
    ("escherichia coli", "ampicillin"),
    ("escherichia coli", "trimethoprim sulfamethoxazole"),
    ("escherichia coli", "ciprofloxacin"),
    ("escherichia coli", "meropenem"),
    ("escherichia coli", "nitrofurantoin"),
    ("klebsiella pneumoniae", "ciprofloxacin"),
    ("klebsiella pneumoniae", "gentamicin"),
    ("klebsiella pneumoniae", "aztreonam"),
    ("salmonella typhi", "ceftriaxone"),
    ("salmonella typhi", "ciprofloxacin"),
    ("salmonella typhi", "azithromycin"),
]

# US cohort keys some Pakistani organisms map to (naming differs across sources).
_US_ORG_ALIAS = {"salmonella typhi": "salmonella enterica"}


def _cell_pct(locale: str, organism: str, drug: str):
    """(percent_susceptible, status) for a cell, or (None, None) if absent."""
    cell = antibiogram_service.get_cell(locale, organism, drug)
    if not cell:
        return None, None
    return cell.get("percent_susceptible"), cell.get("status")


def _build_us_vs_pk_contrast() -> Dict:
    """Data-driven US-vs-Pakistan %-susceptible contrast (M6 keystone chart).

    Emits a row only when Pakistan has a usable value OR gates the drug
    (do_not_use), pairing it with the US value where available. Nothing is
    invented; rows are sorted by absolute divergence (gated rows first).
    """
    rows = []
    for organism, drug in _CONTRAST_PAIRS:
        pk_pct, pk_status = _cell_pct("pakistan", organism, drug)
        gated = pk_status == "do_not_use"
        if pk_pct is None and not gated:
            continue  # no honest Pakistani datapoint
        us_org = _US_ORG_ALIAS.get(organism, organism)
        us_pct, _ = _cell_pct("us_armd", us_org, drug)
        pk_value = 0.0 if gated else float(pk_pct)
        delta = (float(us_pct) - pk_value) if us_pct is not None else None
        rows.append({
            "organism": organism,
            "drug": drug,
            "us_percent_susceptible": None if us_pct is None else round(float(us_pct), 1),
            "pk_percent_susceptible": None if (pk_pct is None and not gated) else round(pk_value, 1),
            "pk_gated": gated,
            "delta": None if delta is None else round(delta, 1),
        })
    rows.sort(key=lambda r: (not r["pk_gated"], -(abs(r["delta"]) if r["delta"] is not None else 0)))
    pk_meta = (antibiogram_service.locales.get("pakistan", {}) or {}).get("meta", {})
    us_meta = (antibiogram_service.locales.get("us_armd", {}) or {}).get("meta", {})
    return {
        "rows": rows,
        "us_source": us_meta.get("display_name"),
        "pk_source": pk_meta.get("display_name"),
        "note": ("US = ARMD (Stanford) proof-of-method antibiogram; Pakistan = provisional "
                 "single-centre seed. Contrast is illustrative, not a validated national comparison."),
    }


# ═════════════════════════════════════════════════════════════════════════════
# V1 routes (CatBoost) — DISABLED. Superseded by V2 ARMD RandomForest routes.
# The block below is commented out (kept for reference) and not mounted in main.py.
# ═════════════════════════════════════════════════════════════════════════════
'''
def _validate_age(age: int, request_id: str) -> None:
    if age < 0 or age > 150:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Age must be between 0 and 150 years.",
            headers={"X-Request-ID": request_id}
        )


def _build_explainability_response(
    organism: str,
    age: int,
    gender: str,
    kidney_function: str,
    severity: str,
    antibiotic: str,
) -> Dict[str, float]:
    return prediction_service.get_feature_importance_for_prediction(
        organism=organism,
        age=age,
        gender=gender,
        kidney_function=kidney_function,
        severity=severity,
        antibiotic=antibiotic,
    )


@router.post(
    "/recommend",
    response_model=AntibioticRecommendationResponse,
    responses={
        200: {"description": "Successful recommendation"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Get antibiotic recommendations",
    description="Get AI-powered antibiotic recommendations with dosing information"
)
async def get_recommendation(request: AntibioticRecommendationRequest, response: Response):
    """
    Get antibiotic recommendations based on patient data.

    This endpoint uses a trained CatBoost model to predict
    antibiotic susceptibility and applies rule-based dosing logic.

    Returns top 3 recommended antibiotics with dosing information.
    """
    request_id = str(uuid4())
    try:
        logger.info(f"[request_id={request_id}] Processing recommendation request for organism: {request.organism}")

        _validate_age(request.age, request_id)

        # Get predictions from ML model
        predictions = prediction_service.predict(
            organism=request.organism.value,
            age=request.age,
            gender=request.gender.value,
            kidney_function=request.kidney_function.value,
            severity=request.severity.value
        )

        # Get top 3 antibiotics with adjusted ranking.
        top_antibiotics = prediction_service.rank_antibiotics(
            predictions=predictions,
            organism=request.organism.value,
            top_k=3
        )

        all_predictions = [
            {
                "antibiotic": antibiotic,
                "probability": round(probability, 3)
            }
            for antibiotic, probability in sorted(
                predictions.items(),
                key=lambda item: item[1],
                reverse=True
            )
        ]

        # Apply dosing rules
        recommendations = []
        for antibiotic, probability in top_antibiotics:
            dosing_info = dosing_engine.get_dosing(
                antibiotic=antibiotic,
                age=request.age,
                kidney_function=request.kidney_function.value,
                severity=request.severity.value
            )

            recommendations.append({
                "antibiotic": antibiotic,
                "probability": round(probability, 3),
                "dose": dosing_info["dose"],
                "route": dosing_info["route"],
                "frequency": dosing_info["frequency"],
                "duration": dosing_info["duration"],
                "clinical_notes": dosing_info["notes"]
            })

        response.headers["X-Request-ID"] = request_id

        return AntibioticRecommendationResponse(
            recommendations=recommendations,
            patient_factors={
                "age": request.age,
                "gender": request.gender.value,
                "kidney_function": request.kidney_function.value,
                "severity": request.severity.value
            },
            organism=request.organism.value,
            all_predictions=all_predictions
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[request_id={request_id}] Error generating recommendation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendation: {str(e)}",
            headers={"X-Request-ID": request_id}
        )


@router.post(
    "/explain",
    response_model=Dict[str, float],
    responses={
        200: {"description": "Successful explanation"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        404: {"model": ErrorResponse, "description": "Antibiotic model not available"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Explain a recommendation",
    description="Return SHAP-based feature importances for a single antibiotic prediction"
)
async def explain_recommendation_post(request: AntibioticExplainRequest, response: Response):
    request_id = str(uuid4())
    try:
        logger.info(
            f"[request_id={request_id}] Processing explanation request for organism: {request.organism}, antibiotic: {request.antibiotic}"
        )
        _validate_age(request.age, request_id)

        explanation = _build_explainability_response(
            organism=request.organism.value,
            age=request.age,
            gender=request.gender.value,
            kidney_function=request.kidney_function.value,
            severity=request.severity.value,
            antibiotic=request.antibiotic,
        )

        response.headers["X-Request-ID"] = request_id
        return explanation
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"[request_id={request_id}] Explanation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"X-Request-ID": request_id}
        )
    except Exception as e:
        logger.error(f"[request_id={request_id}] Error generating explanation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate explanation: {str(e)}",
            headers={"X-Request-ID": request_id}
        )


@router.get(
    "/explain",
    response_model=Dict[str, float],
    responses={
        200: {"description": "Successful explanation"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        404: {"model": ErrorResponse, "description": "Antibiotic model not available"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Explain a recommendation",
    description="Return SHAP-based feature importances for a single antibiotic prediction"
)
async def explain_recommendation_get(
    response: Response,
    organism: str = Query(..., description="Bacterial organism"),
    age: int = Query(..., description="Patient age in years"),
    gender: str = Query(..., description="Patient gender (M/F)"),
    kidney_function: str = Query(..., description="Kidney function status"),
    severity: str = Query(..., description="Infection severity"),
    antibiotic: str = Query(..., description="Antibiotic to explain"),
):
    request_id = str(uuid4())
    try:
        logger.info(
            f"[request_id={request_id}] Processing explanation request for organism: {organism}, antibiotic: {antibiotic}"
        )
        _validate_age(age, request_id)

        explanation = _build_explainability_response(
            organism=organism,
            age=age,
            gender=gender,
            kidney_function=kidney_function,
            severity=severity,
            antibiotic=antibiotic,
        )

        response.headers["X-Request-ID"] = request_id
        return explanation
    except ValueError as e:
        logger.warning(f"[request_id={request_id}] Explanation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"X-Request-ID": request_id}
        )
    except Exception as e:
        logger.error(f"[request_id={request_id}] Error generating explanation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate explanation: {str(e)}",
            headers={"X-Request-ID": request_id}
        )


@router.get(
    "/organisms",
    summary="Get supported organisms",
    description="Get list of bacterial organisms supported by the system"
)
async def get_organisms():
    """
    Get list of supported bacterial organisms.
    """
    from app.schemas.request import OrganismEnum

    return {
        "organisms": [
            {"code": org.value, "name": org.value}
            for org in OrganismEnum
        ]
    }


@router.get(
    "/antibiotics",
    summary="Get available antibiotics",
    description="Get list of antibiotics the system can recommend"
)
async def get_antibiotics():
    """
    Get list of available antibiotics.
    """
    try:
        antibiotics = prediction_service.get_available_antibiotics()
        return {"antibiotics": antibiotics}
    except Exception as e:
        logger.error(f"Error fetching antibiotics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch antibiotic list"
        )


@router.get(
    "/model-info",
    summary="Get model information",
    description="Get model inventory, quality metrics, and training metadata"
)
async def get_model_info():
    """
    Get trained model information and quality metrics.
    """
    try:
        return prediction_service.get_model_info()
    except Exception as e:
        logger.error(f"Error fetching model info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch model information"
        )
'''
# ───────────────────────── End of disabled V1 block ─────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# V2 routes — ARMD RandomForest model
# ─────────────────────────────────────────────────────────────────────────────

v2_router = APIRouter()


@v2_router.get(
    "/organisms",
    summary="Get v2 organisms by culture site",
    description="Return ARMD culture sites and culture-specific organism options for the v2 form",
)
async def get_v2_organisms(culture_description: str | None = Query(None)):
    return clinical_catalog_service.get_catalog(culture_description)


@v2_router.post(
    "/recommend",
    response_model=ARMDRecommendationResponse,
    responses={
        200: {"description": "Successful v2 recommendation"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        503: {"model": ErrorResponse, "description": "ARMD model not loaded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="Get v2 antibiotic recommendations (ARMD model)",
    description=(
        "Get AI-powered antibiotic recommendations using the ARMD RandomForest model. "
        "Accepts richer clinical inputs: culture site, organism, age, gender, lab values (WBC, "
        "creatinine, lactate, procalcitonin), and ward location. Returns top 3 antibiotics with "
        "susceptibility probabilities and dosage information."
    ),
)
async def get_v2_recommendation(request: ARMDRecommendationRequest, response: Response):
    """
    V2 recommendation endpoint using the ARMD RandomForest model.

    The model scores all 32 candidate antibiotics for susceptibility given the patient
    context, returns the top 3, and enriches each with dosage information from the
    hybrid lookup/ML dosage model.
    """
    request_id = str(uuid4())
    response.headers["X-Request-ID"] = request_id

    try:
        logger.info(
            f"[request_id={request_id}] V2 recommend: organism={request.organism!r} "
            f"culture={request.culture_description!r} age={request.age} ward={request.ward} "
            f"locale={request.locale!r}"
        )

        locale = (request.locale or "us_armd").strip().lower()

        # ── Non-US locale (e.g. Pakistan): aggregate ANTIBIOGRAM path (Route A) ──
        # Recommendations are driven by the local antibiogram's %-susceptible, NOT the
        # US-trained RandomForest (Pakistani AMR data is aggregate-only). Gating rules
        # (do_not_use / unknown / below-threshold) come from ANTIBIOGRAM_README §3.
        if locale != "us_armd":
            if not antibiogram_service.has_locale(locale):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(f"Unknown locale '{locale}'. Available: "
                            f"{['us_armd'] + antibiogram_service.available_locales()}."),
                    headers={"X-Request-ID": request_id},
                )
            if not antibiogram_service.is_valid_organism(locale, request.organism):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(f"No local antibiogram for organism '{request.organism}' in locale "
                            f"'{locale}'. Available: {antibiogram_service.organisms(locale)}."),
                    headers={"X-Request-ID": request_id},
                )
            rec = antibiogram_service.recommend(locale, request.organism, top_k=3)
            recommendations = []
            for item in rec["recommendations"]:
                dosage = dosage_service.get_dosage(
                    antibiotic=item["antibiotic"],
                    disease=request.culture_description,
                    age=request.age,
                )
                recommendations.append({
                    "antibiotic": item["antibiotic"],
                    "probability": item["probability"],
                    "dose_range": dosage["dose_range"],
                    "route": dosage["route"],
                    "dose_source": dosage["source"],
                    "basis": "antibiogram",
                    "percent_susceptible": item["percent_susceptible"],
                    "source_id": item.get("source_id"),
                    "confidence": item.get("confidence"),
                })
            patient_factors = {
                "culture_description": request.culture_description,
                "organism": request.organism,
                "age": request.age,
                "gender": request.gender,
                "ward": request.ward.value,
                "locale": locale,
            }
            return ARMDRecommendationResponse(
                recommendations=recommendations,
                patient_factors=patient_factors,
                culture_description=request.culture_description,
                all_predictions=rec["all"],
                locale=locale,
                basis="antibiogram",
                excluded=rec["excluded"],
                antibiogram_meta=rec.get("meta"),
                dose_disclaimer=DOSE_DISCLAIMER,
            )

        # ── Default US/ARMD locale: RandomForest scoring path (unchanged) ──
        if not armd_service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "ARMD model is not trained yet. "
                    "Run armd_model/train_armd.py with the ARMD dataset files in datasets/ "
                    "to generate the model artifacts."
                ),
                headers={"X-Request-ID": request_id},
            )

        if not clinical_catalog_service.is_valid_culture_site(request.culture_description):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported culture site for v2 model: {request.culture_description}",
                headers={"X-Request-ID": request_id},
            )

        if not clinical_catalog_service.is_valid_organism_for_culture(
            request.culture_description,
            request.organism,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Unsupported organism '{request.organism}' for culture site "
                    f"'{request.culture_description}'. Select one of the listed organisms or 'other'."
                ),
                headers={"X-Request-ID": request_id},
            )

        # Map ward enum to binary flags
        ward_icu = 1 if request.ward.value == "icu" else 0
        ward_er = 1 if request.ward.value == "er" else 0
        ward_ip = 1 if request.ward.value == "general" else 0

        top3, all_scores = armd_service.predict(
            culture_description=request.culture_description,
            organism=request.organism,
            age=request.age,
            gender=request.gender,
            wbc=request.wbc,
            cr=request.cr,
            lactate=request.lactate,
            procalcitonin=request.procalcitonin,
            ward_icu=ward_icu,
            ward_er=ward_er,
            ward_ip=ward_ip,
            prior_abx_classes=request.prior_abx_classes,
            prior_organisms=request.prior_organisms,
            explain=True,
        )

        # Enrich top 3 with dosage info
        recommendations = []
        for item in top3:
            dosage = dosage_service.get_dosage(
                antibiotic=item["antibiotic"],
                disease=request.culture_description,
                age=request.age,
            )
            recommendations.append({
                "antibiotic": item["antibiotic"],
                "probability": item["probability"],
                "dose_range": dosage["dose_range"],
                "route": dosage["route"],
                "dose_source": dosage["source"],
                "explanation": item.get("explanation"),
            })

        patient_factors = {
            "culture_description": request.culture_description,
            "organism": request.organism,
            "age": request.age,
            "gender": request.gender,
            "wbc": request.wbc,
            "cr": request.cr,
            "lactate": request.lactate,
            "procalcitonin": request.procalcitonin,
            "ward": request.ward.value,
            "prior_abx_classes": request.prior_abx_classes,
            "prior_organisms": request.prior_organisms,
        }

        return ARMDRecommendationResponse(
            recommendations=recommendations,
            patient_factors=patient_factors,
            culture_description=request.culture_description,
            all_predictions=all_scores,
            locale="us_armd",
            basis="model",
            dose_disclaimer=DOSE_DISCLAIMER,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[request_id={request_id}] V2 recommend failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate v2 recommendation: {exc}",
            headers={"X-Request-ID": request_id},
        )


@v2_router.get(
    "/locales",
    summary="Get available recommendation locales",
    description=(
        "List the locales the recommender supports for the UI toggle. 'us_armd' is "
        "RandomForest-scored (organisms come from the culture catalog). Non-US locales "
        "(e.g. 'pakistan') are antibiogram-driven (Route A) and carry their own organism "
        "list with a per-organism `has_data` flag."
    ),
)
async def get_v2_locales():
    locales = [{
        "id": "us_armd",
        "display_name": "United States · ARMD (RandomForest)",
        "basis": "model",
        "organism_source": "culture_catalog",
        "meta": None,
        "organisms": [],
    }]
    for loc in antibiogram_service.available_locales():
        if loc == "us_armd":
            continue
        organisms = []
        for entry in antibiogram_service.organism_entries(loc):
            rec = antibiogram_service.recommend(loc, entry["name"], top_k=3)
            organisms.append({
                "name": entry["name"],
                "display_name": entry["display_name"],
                "has_data": bool(rec.get("recommendations")),
            })
        data = antibiogram_service.locales.get(loc, {})
        locales.append({
            "id": loc,
            "display_name": (data.get("meta") or {}).get("display_name") or loc,
            "basis": "antibiogram",
            "organism_source": "antibiogram",
            "meta": (data.get("meta") or {}).get("unknown_policy"),
            "organisms": organisms,
        })
    return {"default": "us_armd", "locales": locales}


@v2_router.get(
    "/model-info",
    summary="Get v2 model information",
    description="Get ARMD RandomForest, dosage model, test summary, and training metadata",
)
async def get_v2_model_info():
    recommendation_model = armd_service.get_model_info()
    dosage_model = dosage_service.get_model_info()

    return {
        **recommendation_model,
        'models': {
            'recommendation': recommendation_model,
            'dosage': dosage_model,
        },
        'dosage_model': dosage_model,
        'evaluation': _load_evaluation_summary(),          # M1 rigour → dashboard (M6)
        'us_vs_pk_contrast': _build_us_vs_pk_contrast(),    # keystone contrast chart (M6)
    }
