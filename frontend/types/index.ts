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
