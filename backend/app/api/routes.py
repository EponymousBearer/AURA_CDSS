"""
API routes for the Antibiotic AI CDSS.
v1: CatBoost-based (/api/v1/*)
v2: ARMD RandomForest-based (/api/v2/*)
"""

from fastapi import APIRouter, HTTPException, status, Response, Query
from fastapi.responses import JSONResponse
import logging
from uuid import uuid4
from typing import Dict

from app.schemas.request import (
    AntibioticRecommendationRequest,
    AntibioticRecommendationResponse,
    AntibioticExplainRequest,
    ARMDRecommendationRequest,
    ARMDRecommendationResponse,
    ErrorResponse,
)
from app.services.predictor import PredictionService
from app.services.rules import DosingRuleEngine
from app.services.armd_predictor import ARMDPredictorService
from app.services.dosage_service import DosageService
from app.services.clinical_catalog import ClinicalCatalogService

logger = logging.getLogger(__name__)

router = APIRouter()

# V1 services (CatBoost)
prediction_service = PredictionService()
dosing_engine = DosingRuleEngine()

# V2 services (ARMD RandomForest)
armd_service = ARMDPredictorService()
dosage_service = DosageService()
clinical_catalog_service = ClinicalCatalogService()


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
            f"culture={request.culture_description!r} age={request.age} ward={request.ward}"
        )

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
        }

        return ARMDRecommendationResponse(
            recommendations=recommendations,
            patient_factors=patient_factors,
            culture_description=request.culture_description,
            all_predictions=all_scores,
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
    }
