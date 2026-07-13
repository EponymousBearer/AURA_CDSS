// ─── V1 types (CatBoost model) — DISABLED (superseded by V2 ARMD types) ──────
// Note: ResistanceChartProps and ApiError (further below) remain ACTIVE — they
// are still used by the V2 UI — so they are kept outside this commented block.
/*
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
*/

// ─── Shared types still used by V2 ───────────────────────────────────────────

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

// 'us_armd' = RandomForest (US/ARMD); any other id = antibiogram-driven locale (Route A).
export type LocaleId = 'us_armd' | 'pakistan' | string

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
  locale: LocaleId
}

export interface ARMDRecommendation {
  antibiotic: string
  probability: number
  dose_range: string
  route: string
  dose_source: 'lookup' | 'model' | 'fallback'
  // --- provenance (populated on the antibiogram / Pakistan path) ---
  basis?: 'model' | 'antibiogram'
  percent_susceptible?: number | null
  source_id?: string | null
  confidence?: string | null
}

export interface ARMDRecommendationResponse {
  recommendations: ARMDRecommendation[]
  patient_factors: Record<string, unknown>
  culture_description: string
  all_predictions: { antibiotic: string; probability: number }[]
  // --- locale metadata (additive; US default preserves the original contract) ---
  locale: LocaleId
  basis: 'model' | 'antibiogram'
  excluded?: Record<string, string> | null
  antibiogram_meta?: {
    display_name?: string
    version?: string
    breakpoint_standard?: string
    unknown_policy?: string
    min_isolates_for_filter?: number
  } | null
  dose_disclaimer?: string | null
}

export interface LocaleOrganismOption {
  name: string
  display_name: string
  has_data: boolean
}

export interface LocaleInfo {
  id: LocaleId
  display_name: string
  basis: 'model' | 'antibiogram'
  organism_source: 'culture_catalog' | 'antibiogram'
  meta: string | null
  organisms: LocaleOrganismOption[]
}

export interface LocalesResponse {
  default: LocaleId
  locales: LocaleInfo[]
}

export interface ARMDFormProps {
  onSubmit: (data: ARMDFormData) => void
  loading: boolean
  hasSubmitted?: boolean
  onReset?: () => void
  locale: LocaleId
  localeOrganisms?: LocaleOrganismOption[]
}

export interface ARMDOrganismCatalog {
  culture_sites: string[]
  organisms_by_culture: Record<string, string[]>
}

export interface ARMDResultCardProps {
  recommendation: ARMDRecommendation
  rank: number
}
