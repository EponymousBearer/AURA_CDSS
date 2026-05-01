"use client";

import axios from "axios";
import { useState } from "react";
import Link from "next/link";
import PatientForm from "@/components/PatientForm";
import ResultCardV2 from "@/components/ResultCardV2";
import ResistanceChart from "@/components/ResistanceChart";
import DisclaimerBanner from "@/components/DisclaimerBanner";
import { getARMDRecommendation } from "@/services/api";
import {
  ARMDFormData,
  ARMDRecommendation,
  ApiError,
} from "@/types";

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ARMDRecommendation[] | null>(null);
  const [allPredictions, setAllPredictions] = useState<
    { antibiotic: string; probability: number }[] | null
  >(null);
  const [cultureLabel, setCultureLabel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [resultTimestamp, setResultTimestamp] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<ARMDFormData | null>(null);

  const submit = async (formData: ARMDFormData) => {
    setLoading(true);
    setError(null);
    setResults(null);
    setAllPredictions(null);
    setResultTimestamp(null);
    setCultureLabel(
      `${formData.organism} · ${formData.culture_description}`
    );
    setLastRequest(formData);

    try {
      const response = await getARMDRecommendation(formData);
      setResults(response.recommendations);
      setAllPredictions(response.all_predictions);
      setResultTimestamp(new Date().toLocaleString());
    } catch (err) {
      if (axios.isAxiosError(err)) {
        if (!err.response) {
          setError(
            "The backend service is unreachable. Please ensure the FastAPI server is running on http://localhost:8000."
          );
        } else if (err.response.status === 503) {
          setError(
            "The ARMD model has not been trained yet. " +
              "Add the ARMD dataset files to datasets/ and run armd_model/train_armd.py, " +
              "then armd_model/train_dosage.py to generate the model artifacts."
          );
        } else {
          setError(
            (err.response.data as ApiError | undefined)?.detail ||
              "The server returned an unexpected error. Please retry."
          );
        }
      } else {
        setError("An unexpected error occurred while fetching recommendations.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastRequest) submit(lastRequest);
  };

  const handleReset = () => {
    setResults(null);
    setAllPredictions(null);
    setError(null);
    setCultureLabel("");
    setResultTimestamp(null);
    setLastRequest(null);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <DisclaimerBanner
        type="warning"
        message={
          <span>For Academic &amp; Research Use Only — Not for Clinical Practice</span>
        }
      />

      <div className="container mx-auto px-4 py-10">
        {/* ── Hero ── */}
        <section className="mx-auto mb-12 max-w-5xl text-center">
          <h1 className="bg-gradient-to-r from-blue-700 via-indigo-600 to-sky-500 bg-clip-text text-5xl font-black tracking-tight text-transparent sm:text-6xl md:text-7xl">
            AURA
          </h1>
          <p className="mx-auto mt-3 max-w-3xl text-lg text-slate-600 sm:text-xl">
            Antibiotic Clinical Decision Support · ARMD RandomForest Model
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3 text-sm text-slate-600">
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">
              32 Antibiotics
            </span>
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">
              ARMD Dataset
            </span>
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">
              RandomForest
            </span>
            <span className="rounded-full bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200">
              Lab-aware Dosing
            </span>
          </div>
        </section>

        <div className="max-w-6xl mx-auto">
          {/* ── Form ── */}
          <div className="mb-8">
            <PatientForm
              onSubmit={submit}
              loading={loading}
              hasSubmitted={Boolean(results)}
              onReset={handleReset}
            />
          </div>

          {/* ── Error ── */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-800 px-6 py-4 rounded-xl mb-8 space-y-3">
              <p className="font-medium">{error}</p>
              <button
                type="button"
                onClick={handleRetry}
                disabled={!lastRequest || loading}
                className="rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Retry
              </button>
            </div>
          )}

          {/* ── Results ── */}
          {results && (
            <div className="space-y-6">
              {/* Results header */}
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">
                  Top Recommendations
                </h2>
                <div className="text-right text-sm text-gray-500">
                  <div className="font-medium capitalize">{cultureLabel}</div>
                  {resultTimestamp && (
                    <div className="mt-0.5 text-xs">
                      Generated at{" "}
                      <span className="font-medium">{resultTimestamp}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Recommendation cards */}
              <div className="grid gap-6 md:grid-cols-3">
                {results.map((rec, i) => (
                  <ResultCardV2
                    key={rec.antibiotic}
                    recommendation={rec}
                    rank={i + 1}
                  />
                ))}
              </div>

              {/* Full resistance chart */}
              {allPredictions && (
                <ResistanceChart
                  allPredictions={allPredictions}
                  organism={cultureLabel}
                />
              )}

              {/* Clinical disclaimer */}
              <div className="mt-4">
                <DisclaimerBanner
                  type="info"
                  message={
                    <span>
                      <span className="font-semibold">Clinical Disclaimer:</span>{" "}
                      AI-generated recommendations must be verified against current
                      local susceptibility data, institutional stewardship protocols,
                      and specialist guidance. Final prescribing decisions rest with
                      the clinician.
                    </span>
                  }
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <footer className="mt-16 border-t border-slate-200 pt-6 text-center text-sm text-slate-500 space-y-2">
          <div className="flex flex-wrap items-center justify-center gap-6">
            <Link
              href="/model-info"
              className="inline-flex items-center text-blue-700 hover:text-blue-900 font-medium transition-colors"
            >
              Model Performance Dashboard →
            </Link>
          </div>
        </footer>
      </div>
    </main>
  );
}
