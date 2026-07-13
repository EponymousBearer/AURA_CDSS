"use client";

import axios from "axios";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import PatientForm from "@/components/PatientForm";
import ResultCardV2 from "@/components/ResultCardV2";
import ResistanceChart from "@/components/ResistanceChart";
import DisclaimerBanner from "@/components/DisclaimerBanner";
import LocaleToggle from "@/components/LocaleToggle";
import { getARMDRecommendation, getARMDLocales } from "@/services/api";
import {
  ARMDFormData,
  ARMDRecommendation,
  ARMDRecommendationResponse,
  ApiError,
  LocaleId,
  LocaleInfo,
} from "@/types";

// Human-readable reasons for the antibiogram `excluded` map.
function excludedReason(code: string): string {
  if (code.startsWith("below_threshold")) return "Too few local isolates to report";
  if (code === "gated_do_not_use") return "Locally unreliable — gated off (do not use)";
  if (code === "gated_unknown") return "No local susceptibility data";
  if (code === "not_tested") return "Not tested in the local antibiogram";
  if (code === "no_value") return "No susceptibility value recorded";
  return code;
}

function titleCase(value: string) {
  return value
    .split(" ")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

export default function Home() {
  const [locales, setLocales] = useState<LocaleInfo[]>([]);
  const [locale, setLocale] = useState<LocaleId>("us_armd");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ARMDRecommendation[] | null>(null);
  const [meta, setMeta] = useState<ARMDRecommendationResponse | null>(null);
  const [allPredictions, setAllPredictions] = useState<
    { antibiotic: string; probability: number }[] | null
  >(null);
  const [cultureLabel, setCultureLabel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [resultTimestamp, setResultTimestamp] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<ARMDFormData | null>(null);

  useEffect(() => {
    let mounted = true;
    getARMDLocales()
      .then((res) => {
        if (mounted) setLocales(res.locales);
      })
      .catch(() => {
        // Backend unreachable — fall back to US-only so the app still renders.
        if (mounted)
          setLocales([
            {
              id: "us_armd",
              display_name: "United States · ARMD (RandomForest)",
              basis: "model",
              organism_source: "culture_catalog",
              meta: null,
              organisms: [],
            },
          ]);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const currentLocale = useMemo(
    () => locales.find((l) => l.id === locale),
    [locales, locale]
  );
  const isAntibiogram = locale !== "us_armd";

  const clearResults = () => {
    setResults(null);
    setMeta(null);
    setAllPredictions(null);
    setError(null);
    setResultTimestamp(null);
    setCultureLabel("");
    setLastRequest(null);
  };

  const handleLocaleChange = (next: LocaleId) => {
    if (next === locale) return;
    setLocale(next);
    clearResults();
  };

  const submit = async (formData: ARMDFormData) => {
    setLoading(true);
    setError(null);
    setResults(null);
    setMeta(null);
    setAllPredictions(null);
    setResultTimestamp(null);
    setCultureLabel(`${formData.organism} · ${formData.culture_description}`);
    setLastRequest(formData);

    try {
      const response = await getARMDRecommendation(formData);
      setResults(response.recommendations);
      setMeta(response);
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

  const excludedEntries = meta?.excluded ? Object.entries(meta.excluded) : [];

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
        <section className="mx-auto mb-10 max-w-5xl text-center">
          <h1 className="bg-gradient-to-r from-blue-700 via-indigo-600 to-sky-500 bg-clip-text text-5xl font-black tracking-tight text-transparent sm:text-6xl md:text-7xl">
            AURA
          </h1>
          <p className="mx-auto mt-3 max-w-3xl text-lg text-slate-600 sm:text-xl">
            Antibiotic Clinical Decision Support · Locale-aware empiric guidance
          </p>
        </section>

        {/* ── Locale toggle (the localisation money-shot) ── */}
        {locales.length > 1 && (
          <LocaleToggle
            value={locale}
            locales={locales}
            onChange={handleLocaleChange}
            disabled={loading}
          />
        )}

        <div className="max-w-6xl mx-auto">
          {/* Locale context strip */}
          {currentLocale && (
            <div
              className={`mb-6 rounded-xl border px-4 py-3 text-sm ${
                isAntibiogram
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "border-blue-200 bg-blue-50 text-blue-900"
              }`}
            >
              {isAntibiogram ? (
                <span>
                  <span className="font-semibold">Antibiogram mode ({titleCase(locale)}).</span>{" "}
                  Recommendations are driven by the <em>local antibiogram</em> (aggregate
                  %-susceptible), <span className="font-semibold">not</span> the US-trained model.
                  Drugs that are locally unreliable are gated off.
                </span>
              ) : (
                <span>
                  <span className="font-semibold">Model mode (United States · ARMD).</span>{" "}
                  Recommendations come from the RandomForest scoring the patient against the ARMD
                  cohort, filtered by the US organism–antibiotic panel.
                </span>
              )}
            </div>
          )}

          {/* ── Form ── */}
          <div className="mb-8">
            <PatientForm
              key={locale}
              onSubmit={submit}
              loading={loading}
              hasSubmitted={Boolean(results)}
              onReset={clearResults}
              locale={locale}
              localeOrganisms={currentLocale?.organisms ?? []}
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

              {/* Antibiogram provenance (locale path only) */}
              {meta?.basis === "antibiogram" && meta.antibiogram_meta && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-5 py-4 text-sm text-emerald-900">
                  <p className="font-semibold">
                    Source: {meta.antibiogram_meta.display_name}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-emerald-800">
                    {meta.antibiogram_meta.breakpoint_standard && (
                      <span>Breakpoints: {meta.antibiogram_meta.breakpoint_standard}</span>
                    )}
                    {meta.antibiogram_meta.version && (
                      <span>Version: {meta.antibiogram_meta.version}</span>
                    )}
                    {meta.antibiogram_meta.unknown_policy && (
                      <span>Unknown policy: {meta.antibiogram_meta.unknown_policy}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Empty-state (organism with no local data) */}
              {results.length === 0 ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-6 text-amber-900">
                  No local antibiogram data is available for this organism yet
                  {isAntibiogram ? " (national data pending)" : ""}. Try another organism.
                </div>
              ) : (
                <div className="grid gap-6 md:grid-cols-3">
                  {results.map((rec, i) => (
                    <ResultCardV2
                      key={rec.antibiotic}
                      recommendation={rec}
                      rank={i + 1}
                    />
                  ))}
                </div>
              )}

              {/* Excluded-by-antibiogram panel (the localisation highlight) */}
              {excludedEntries.length > 0 && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-5 py-4">
                  <p className="text-sm font-semibold text-rose-900">
                    Excluded by the {titleCase(locale)} antibiogram
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {excludedEntries.map(([drug, code]) => (
                      <span
                        key={drug}
                        title={excludedReason(code)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-white px-3 py-1 text-xs text-rose-700"
                      >
                        <span className="font-semibold capitalize line-through decoration-rose-400">
                          {drug}
                        </span>
                        <span className="text-rose-400">·</span>
                        <span>{excludedReason(code)}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Full resistance / susceptibility chart */}
              {allPredictions && allPredictions.length > 0 && (
                <ResistanceChart
                  allPredictions={allPredictions}
                  organism={cultureLabel}
                />
              )}

              {/* Clinical disclaimer */}
              <div className="mt-4 space-y-3">
                {meta?.dose_disclaimer && (
                  <DisclaimerBanner type="info" message={<span>{meta.dose_disclaimer}</span>} />
                )}
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
