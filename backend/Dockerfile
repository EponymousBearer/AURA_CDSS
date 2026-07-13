FROM python:3.11-slim

WORKDIR /app

# NOTE: build context must be the REPO ROOT (paths below are repo-root-relative).
# On Render set: Root Directory = (blank), Dockerfile Path = backend/Dockerfile.

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/app/ ./app/
# V2 model artifacts. The large dose/route .pkl stay out of git (rebuilt locally);
# the committed CALIBRATED RF recommender, dose_route_lookup.csv and antibiogram panel
# ship here. Missing dose ML models -> dosage_service falls back to lookup + static rules.
COPY armd_model/artifacts/ ./armd_model/artifacts/
# Per-locale antibiograms (M4) — the Pakistan/Route-A path + US-vs-PK contrast need these.
# LocaleAntibiogramService resolves ./antibiograms relative to /app by default.
COPY backend/antibiograms/ ./antibiograms/
# M1 evaluation metrics surfaced on /model-info (M6). Only metrics.json is needed by the
# API; the figures themselves are served by the frontend (frontend/public/figures).
COPY reports/metrics.json ./reports/metrics.json

# Tell the V2 services where the model artifacts + evaluation metrics live.
ENV ARMD_ARTIFACTS_DIR=/app/armd_model/artifacts
ENV REPORTS_DIR=/app/reports

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Render injects $PORT and probes it via healthCheckPath (/health); bind to it.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
