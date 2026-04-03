'use client'

import axios from 'axios'
import { useState } from 'react'
import Link from 'next/link'
import PatientForm from '@/components/PatientForm'
import ResultCard from '@/components/ResultCard'
import ResistanceChart from '@/components/ResistanceChart'
import DisclaimerBanner from '@/components/DisclaimerBanner'
import { getRecommendation } from '@/services/api'
import { Recommendation, ApiError, PatientFormData } from '@/types'

export default function Home() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<Recommendation[] | null>(null)
  const [allPredictions, setAllPredictions] = useState<{ antibiotic: string; probability: number }[] | null>(null)
  const [organism, setOrganism] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [resultTimestamp, setResultTimestamp] = useState<string | null>(null)
  const [lastRequest, setLastRequest] = useState<PatientFormData | null>(null)

  const submitRecommendation = async (formData: PatientFormData) => {
    setLoading(true)
    setError(null)
    setResults(null)
    setAllPredictions(null)
    setResultTimestamp(null)
    setOrganism(formData.organism)
    setLastRequest(formData)

    try {
      const response = await getRecommendation(formData)
      setResults(response.recommendations)
      setAllPredictions(response.allPredictions)
      setResultTimestamp(new Date().toLocaleString())
    } catch (err) {
      if (axios.isAxiosError(err)) {
        if (!err.response) {
          setError('The backend service is unreachable. Please ensure the FastAPI server is running on http://localhost:8000.')
        } else if (err.response.status >= 400 && err.response.status < 500) {
          setError(
            (err.response.data as { detail?: string } | undefined)?.detail ||
              'The request was rejected by the API. Please check the input values and try again.'
          )
        } else {
          setError(
            (err.response.data as { detail?: string } | undefined)?.detail ||
              'The server returned an unexpected error. Please retry.'
          )
        }
      } else {
        setError('An unexpected error occurred while fetching recommendations.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (formData: PatientFormData) => {
    await submitRecommendation(formData)
  }

  const handleRetry = async () => {
    if (lastRequest) {
      await submitRecommendation(lastRequest)
    }
  }

  const handleReset = () => {
    setResults(null)
    setAllPredictions(null)
    setError(null)
    setOrganism('')
    setResultTimestamp(null)
    setLastRequest(null)
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <DisclaimerBanner
        type="warning"
        message={<span>For Academic &amp; Research Use Only - Not for Clinical Practice</span>}
      />

      <div className="container mx-auto px-4 py-10">
        {/* Hero */}
        <section className="mx-auto mb-12 max-w-5xl text-center">
          <div className="mb-5 inline-flex items-center rounded-full border border-blue-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-blue-700 shadow-sm">
            FYP Research Project — CDSS
          </div>
          <h1 className="bg-gradient-to-r from-blue-700 via-indigo-600 to-sky-500 bg-clip-text text-5xl font-black tracking-tight text-transparent sm:text-6xl md:text-7xl">
            Antibiotic AI
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-lg text-slate-600 sm:text-xl">
            Clinical Decision Support System powered by CatBoost Machine Learning
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3 text-sm text-slate-600">
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">26 Antibiotics Analyzed</span>
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">Real Dryad Dataset</span>
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">CatBoost Models</span>
          </div>
        </section>

        <div className="max-w-6xl mx-auto">
          {/* Form Section */}
          <div className="mb-8">
            <PatientForm
              onSubmit={handleSubmit}
              loading={loading}
              hasSubmitted={Boolean(results)}
              onReset={handleReset}
            />
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-800 px-6 py-4 rounded-lg mb-8 space-y-3">
              <p className="font-medium">{error}</p>
              <button
                type="button"
                onClick={handleRetry}
                disabled={!lastRequest || loading}
                className="rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Retry last request
              </button>
            </div>
          )}

          {/* Results Section */}
          {results && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">
                  Recommended Antibiotics
                </h2>
                <div className="text-right text-sm text-gray-500">
                  <div>
                    Target Organism: <span className="font-medium">{organism}</span>
                  </div>
                  {resultTimestamp && (
                    <div className="mt-1">
                      Recommendations generated at <span className="font-medium">{resultTimestamp}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid gap-6 md:grid-cols-3">
                {results.map((recommendation, index) => (
                  <ResultCard
                    key={recommendation.antibiotic}
                    recommendation={recommendation}
                    rank={index + 1}
                    patientData={lastRequest}
                  />
                ))}
              </div>

              {allPredictions && (
                <ResistanceChart allPredictions={allPredictions} organism={organism} />
              )}

              {/* Disclaimer */}
              <div className="mt-8">
                <DisclaimerBanner
                  type="info"
                  message={
                    <span>
                      <span className="font-semibold">Clinical Disclaimer:</span> This tool provides AI-generated recommendations based on predictive models. Always verify with current local susceptibility patterns and clinical guidelines. Final treatment decisions should consider patient-specific factors and local antibiograms.
                    </span>
                  }
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-16 border-t border-slate-200 pt-6 text-center text-sm text-slate-500">
          <p>Built for Final Year Project | Dataset: Dryad Digital Repository | Model: CatBoost</p>
          <Link
            href="/model-info"
            className="mt-3 inline-flex items-center text-blue-700 hover:text-blue-900 font-medium transition-colors"
          >
            View model performance dashboard
          </Link>
        </footer>
      </div>
    </main>
  )
}
