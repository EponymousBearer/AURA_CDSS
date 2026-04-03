"""
API routes for the Antibiotic AI CDSS.
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
    ErrorResponse
)
from app.services.predictor import PredictionService
from app.services.rules import DosingRuleEngine

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
prediction_service = PredictionService()
dosing_engine = DosingRuleEngine()


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
