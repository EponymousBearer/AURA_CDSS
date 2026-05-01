"""
Pydantic schemas for request/response validation.
v1 schemas: CatBoost-based (organism/age/gender/kidney_function/severity)
v2 schemas: ARMD RandomForest (culture_description/organism/age/gender/labs/ward)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class OrganismEnum(str, Enum):
    """Supported bacterial organisms."""
    E_COLI = "E. coli"
    K_PNEUMONIAE = "K. pneumoniae"
    P_AERUGINOSA = "P. aeruginosa"
    A_BAUMANNII = "A. baumannii"
    S_AUREUS = "S. aureus"
    E_FAECIUM = "E. faecium"
    S_PNEUMONIAE = "S. pneumoniae"
    ENTEROCOCCUS_SPP = "Enterococcus spp"
    COAG_NEGATIVE_STAPHYLOCOCCUS = "COAG NEGATIVE STAPHYLOCOCCUS"
    KLEBSIELLA_OXYTOCA = "KLEBSIELLA OXYTOCA"
    PROTEUS_MIRABILIS = "PROTEUS MIRABILIS"
    STAPHYLOCOCCUS_EPIDERMIDIS = "STAPHYLOCOCCUS EPIDERMIDIS"
    ENTEROCOCCUS_FAECALIS = "ENTEROCOCCUS FAECALIS"
    OTHER = "Other"


class GenderEnum(str, Enum):
    """Patient gender options."""
    MALE = "M"
    FEMALE = "F"


class KidneyFunctionEnum(str, Enum):
    """Kidney function levels."""
    NORMAL = "normal"
    MILD = "mild"
    LOW = "low"
    SEVERE = "severe"


class SeverityEnum(str, Enum):
    """Infection severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AntibioticRecommendationRequest(BaseModel):
    """
    Request schema for antibiotic recommendation.

    Contains patient demographics and clinical information
    used to predict antibiotic susceptibility.
    """
    organism: OrganismEnum = Field(
        ...,
        description="Bacterial organism causing the infection"
    )
    age: int = Field(
        ...,
        description="Patient age in years"
    )
    gender: GenderEnum = Field(
        ...,
        description="Patient gender (M/F)"
    )
    kidney_function: KidneyFunctionEnum = Field(
        ...,
        description="Kidney function status (normal/mild/low/severe)"
    )
    severity: SeverityEnum = Field(
        ...,
        description="Infection severity level (low/medium/high/critical)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "organism": "E. coli",
                "age": 65,
                "gender": "F",
                "kidney_function": "normal",
                "severity": "medium"
            }
        }


class AntibioticResult(BaseModel):
    """
    Single antibiotic recommendation result.
    """
    antibiotic: str = Field(..., description="Antibiotic name")
    probability: float = Field(
        ...,
        ge=0,
        le=1,
        description="Predicted probability of susceptibility"
    )
    dose: str = Field(..., description="Recommended dose")
    route: str = Field(..., description="Route of administration (IV/PO)")
    frequency: str = Field(..., description="Dosing frequency")
    duration: str = Field(..., description="Recommended duration")
    clinical_notes: str = Field(..., description="Clinical guidance notes")


class AntibioticPrediction(BaseModel):
    """Raw susceptibility prediction for a single antibiotic."""
    antibiotic: str = Field(..., description="Antibiotic name")
    probability: float = Field(
        ...,
        ge=0,
        le=1,
        description="Predicted probability of susceptibility"
    )


class AntibioticRecommendationResponse(BaseModel):
    """
    Response schema for antibiotic recommendations.

    Returns top 3 recommended antibiotics with dosing information.
    """
    recommendations: List[AntibioticResult] = Field(
        ...,
        min_length=0,
        max_length=3,
        description="Top 3 antibiotic recommendations"
    )
    patient_factors: Dict[str, Any] = Field(
        ...,
        description="Patient factors considered in recommendation"
    )
    organism: str = Field(..., description="Target organism")
    all_predictions: List[AntibioticPrediction] = Field(
        ...,
        description="All antibiotic susceptibility predictions"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "recommendations": [
                    {
                        "antibiotic": "Ceftriaxone",
                        "probability": 0.92,
                        "dose": "1 g",
                        "route": "IV",
                        "frequency": "Every 24 hours",
                        "duration": "7-14 days",
                        "clinical_notes": "First-line therapy for susceptible isolates"
                    }
                ],
                "patient_factors": {
                    "age": 65,
                    "kidney_function": "normal",
                    "severity": "medium"
                },
                "organism": "E. coli",
                "all_predictions": [
                    {
                        "antibiotic": "Ceftriaxone",
                        "probability": 0.92
                    }
                ]
            }
        }


class AntibioticExplainRequest(AntibioticRecommendationRequest):
    """Request schema for explainability queries."""

    antibiotic: str = Field(..., description="Antibiotic to explain")

    class Config:
        json_schema_extra = {
            "example": {
                "organism": "E. coli",
                "age": 65,
                "gender": "F",
                "kidney_function": "normal",
                "severity": "medium",
                "antibiotic": "Ceftriaxone"
            }
        }


class ErrorResponse(BaseModel):
    """
    Error response schema.
    """
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")
    suggestion: Optional[str] = Field(None, description="Suggested action")


# ─────────────────────────────────────────────────────────────────────────────
# V2 schemas — ARMD RandomForest model
# ─────────────────────────────────────────────────────────────────────────────

class WardEnum(str, Enum):
    GENERAL = "general"
    ICU = "icu"
    ER = "er"


class ARMDRecommendationRequest(BaseModel):
    """
    Request schema for v2 ARMD-based antibiotic recommendation.
    Uses richer clinical inputs including lab values and ward location.
    """
    culture_description: str = Field(
        ...,
        description="Culture site/type (e.g. 'urine', 'blood', 'wound')",
        min_length=1,
        max_length=200,
    )
    organism: str = Field(
        ...,
        description="Infecting organism (free text, lowercased internally)",
        min_length=1,
        max_length=200,
    )
    age: int = Field(..., description="Patient age in years", ge=0, le=150)
    gender: str = Field(..., description="Patient gender: 'male' or 'female'")
    wbc: Optional[float] = Field(None, description="WBC count (×10³/μL)", ge=0)
    cr: Optional[float] = Field(None, description="Creatinine (mg/dL)", ge=0)
    lactate: Optional[float] = Field(None, description="Lactate (mmol/L)", ge=0)
    procalcitonin: Optional[float] = Field(None, description="Procalcitonin (ng/mL)", ge=0)
    ward: WardEnum = Field(WardEnum.GENERAL, description="Patient ward location")

    class Config:
        json_schema_extra = {
            "example": {
                "culture_description": "urine",
                "organism": "klebsiella pneumoniae",
                "age": 45,
                "gender": "female",
                "wbc": 12.5,
                "cr": 1.2,
                "lactate": 1.8,
                "procalcitonin": 2.5,
                "ward": "er",
            }
        }


class ARMDResult(BaseModel):
    """Single v2 antibiotic recommendation result."""
    antibiotic: str = Field(..., description="Antibiotic name")
    probability: float = Field(..., ge=0, le=1, description="Predicted susceptibility probability")
    dose_range: str = Field(..., description="Recommended dose range")
    route: str = Field(..., description="Route of administration (IV/PO/IM)")
    dose_source: str = Field(..., description="Source of dosage: lookup | model | fallback")


class ARMDRecommendationResponse(BaseModel):
    """Response schema for v2 ARMD recommendations."""
    recommendations: List[ARMDResult] = Field(..., description="Top 3 antibiotic recommendations")
    patient_factors: Dict[str, Any] = Field(..., description="Echo of patient input factors")
    culture_description: str = Field(..., description="Culture site used for dosage lookup")
    all_predictions: List[Dict[str, Any]] = Field(
        ..., description="All antibiotics sorted by susceptibility probability"
    )
