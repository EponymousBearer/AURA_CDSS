import axios from 'axios'
import { PatientFormData, RecommendationResponse } from '@/types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

export async function getRecommendation(
  data: PatientFormData
): Promise<RecommendationResponse> {
  const response = await api.post('/api/v1/recommend', data)
  const payload = response.data

  return {
    ...payload,
    allPredictions: payload.all_predictions ?? payload.allPredictions ?? [],
  }
}

export async function getOrganisms() {
  const response = await api.get('/api/v1/organisms')
  return response.data
}

export async function getAntibiotics() {
  const response = await api.get('/api/v1/antibiotics')
  return response.data
}

export type FeatureImportanceResponse = Record<string, number>

export async function getExplanation(
  data: PatientFormData,
  antibiotic: string
): Promise<FeatureImportanceResponse> {
  const response = await api.get('/api/v1/explain', {
    params: {
      organism: data.organism,
      age: data.age,
      gender: data.gender,
      kidney_function: data.kidney_function,
      severity: data.severity,
      antibiotic,
    },
  })

  return response.data
}

export interface ModelAntibioticInfo {
  name: string
  auc: number
  f1: number
  accuracy: number
  status: 'included' | 'excluded_low_auc' | 'excluded_single_class' | string
}

export interface ModelInfoResponse {
  total_models_loaded: number
  model_trained_at: string | null
  training_samples: number
  n_antibiotics: number
  antibiotics: ModelAntibioticInfo[]
}

export interface AntibioticPrediction {
  antibiotic: string
  probability: number
}

export interface RecommendationWithPredictionsResponse extends RecommendationResponse {
  allPredictions: AntibioticPrediction[]
}

export async function getModelInfo(): Promise<ModelInfoResponse> {
  const response = await api.get('/api/v1/model-info')
  return response.data
}
