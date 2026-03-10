"""
Canonical health check endpoints shared across all V-CAD services.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Standard health check response."""
    status: str
    version: str
    service: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check():
    """Health check endpoint to verify the service is running."""
    from app.config import settings
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        service=settings.APP_NAME,
    )


@router.get("/", summary="Service info")
async def root():
    """Root endpoint with service info and docs link."""
    from app.config import settings
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
    }
