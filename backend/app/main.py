"""
FastAPI application for Antibiotic AI Clinical Decision Support System.
Main entry point for the backend API.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
import time

from app.api.routes import router as api_router
from app.utils.logger import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Antibiotic AI Clinical Decision Support System",
    description="AI-powered antibiotic recommendations with rule-based dosing",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Log service readiness and model loading status at startup."""
    from app.api.routes import prediction_service

    environment = os.getenv("ENVIRONMENT", "development")
    model_loaded = len(prediction_service.antibiotic_list) > 0 and len(prediction_service.models) > 0
    logger.info(
        "Startup status | environment=%s | model_loaded=%s | antibiotics=%s",
        environment,
        model_loaded,
        len(prediction_service.antibiotic_list),
    )


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for logging requests and timing."""
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")

    try:
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"Response: {response.status_code} | "
            f"Duration: {duration:.3f}s | "
            f"Path: {request.url.path}"
        )

        return response

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if app.debug else "An unexpected error occurred"
        }
    )


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Antibiotic AI CDSS API",
        "version": "1.0.0",
        "status": "operational",
        "docs_url": "/docs",
        "endpoints": {
            "recommend": "/api/v1/recommend"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "antibiotic-ai-cdss"
    }


# Include API routes
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
