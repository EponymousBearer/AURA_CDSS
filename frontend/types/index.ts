// ─── V1 types (CatBoost model) ───────────────────────────────────────────────

export interface PatientFormData {
  organism: string
  age: number
  gender: string
  kidney_function: 'normal' | 'mild' | 'low' | 'severe'
  severity: 'low' | 'medium' | 'high' | 'critical'
}

export interface Recommendation {
  antibiotic: string
  probability: number
  dose: string
  route: string
  frequency: string
  duration: string
  clinical_notes: string
}

export interface RecommendationResponse {
  recommendations: Recommendation[]
  allPredictions: {
    antibiotic: string
    probability: number
  }[]
  patient_factors: {
    age: number
    gender: string
    kidney_function: 'normal' | 'mild' | 'low' | 'severe'
    severity: 'low' | 'medium' | 'high' | 'critical'
  }
  organism: string
}

export interface PatientFormProps {
  onSubmit: (data: PatientFormData) => void
  loading: boolean
  hasSubmitted?: boolean
  onReset?: () => void
}

export interface ResultCardProps {
  recommendation: Recommendation
  rank: number
  patientData: PatientFormData | null
}

export interface ExplainabilityModalData {
  antibiotic: string
  featureImportances: Record<string, number>
}

export interface ResistanceChartProps {
  allPredictions: {
    antibiotic: string
    probability: number
  }[]
  organism: string
}

export interface ApiError {
  error?: string
  detail?: string
  suggestion?: string
}

// ─── V2 types (ARMD RandomForest model) ──────────────────────────────────────

export type WardType = 'general' | 'icu' | 'er'

export interface ARMDFormData {
  culture_description: string
  organism: string
  age: number
  gender: string        // 'male' | 'female'
  wbc: number | null
  cr: number | null
  lactate: number | null
  procalcitonin: number | null
  ward: WardType
}

export interface ARMDRecommendation {
  antibiotic: string
  probability: number
  dose_range: string
  route: string
  dose_source: 'lookup' | 'model' | 'fallback'
}

export interface ARMDRecommendationResponse {
  recommendations: ARMDRecommendation[]
  patient_factors: Record<string, unknown>
  culture_description: string
  all_predictions: { antibiotic: string; probability: number }[]
}

export interface ARMDFormProps {
  onSubmit: (data: ARMDFormData) => void
  loading: boolean
  hasSubmitted?: boolean
  onReset?: () => void
}

export interface ARMDOrganismCatalog {
  culture_sites: string[]
  organisms_by_culture: Record<string, string[]>
}

export interface ARMDResultCardProps {
  recommendation: ARMDRecommendation
  rank: number
}
