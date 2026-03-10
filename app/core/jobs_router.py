"""
Canonical generic job endpoints shared across all V-CAD services.

Provides a factory function `create_jobs_router()` that returns an APIRouter
with standard job polling/management endpoints. Services add their own
job-creation endpoints separately.
"""

import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.job_manager import get_job_manager, JobStatus

logger = logging.getLogger(__name__)


# ============================================================================
# Response Models
# ============================================================================

class JobCreatedResponse(BaseModel):
    """Response when a job is created."""
    job_id: str = Field(..., description="Unique job identifier for polling")
    status: str = Field(..., description="Initial job status")
    message: str = Field(..., description="Status message")
    poll_url: str = Field(..., description="URL to poll for job status")


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    type: str
    status: JobStatus
    progress: int
    message: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Job result (only included for completed jobs when requested)",
    )


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: List[JobStatusResponse]
    total: int


# ============================================================================
# Helpers
# ============================================================================

def create_job_response(job, job_type: str, prefix: str = "/jobs") -> JobCreatedResponse:
    """Helper to create a standard job-created response."""
    return JobCreatedResponse(
        job_id=job.id,
        status=job.status.value,
        message=f"{job_type} job created",
        poll_url=f"{prefix}/{job.id}",
    )


def _job_to_status_response(job, include_result: bool = False) -> JobStatusResponse:
    """Convert a Job model to a JobStatusResponse."""
    return JobStatusResponse(
        job_id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        message=job.message,
        error=job.error,
        error_code=job.error_code,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result=job.result if include_result and job.status == JobStatus.COMPLETED else None,
    )


# ============================================================================
# Factory
# ============================================================================

def create_jobs_router(
    prefix: str = "/jobs",
    tags: Optional[list] = None,
) -> APIRouter:
    """
    Create an APIRouter with standard job management endpoints.

    Returns a router with:
      GET  /{job_id}        - Get job status
      GET  /{job_id}/result - Get job result
      DELETE /{job_id}      - Cancel job
      GET  /                - List jobs

    Services should add their own POST endpoints for job creation.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["jobs"])

    @router.get("/{job_id}", response_model=JobStatusResponse, summary="Get job status")
    async def get_job_status(job_id: str, include_result: bool = False):
        """
        Get the status of a job.

        Poll this endpoint until status is 'completed' or 'failed'.
        """
        job_manager = get_job_manager()
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return _job_to_status_response(job, include_result=include_result)

    @router.get("/{job_id}/result", summary="Get job result")
    async def get_job_result(job_id: str):
        """Get the result of a completed job."""
        job_manager = get_job_manager()
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        if job.status == JobStatus.PENDING:
            raise HTTPException(status_code=202, detail="Job is still pending")
        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=202, detail="Job is still running")
        if job.status == JobStatus.FAILED:
            status_code = job.error_code or 500
            raise HTTPException(status_code=status_code, detail=job.error or "Job failed")
        return job.result

    @router.delete("/{job_id}", summary="Cancel job")
    async def cancel_job(job_id: str):
        """Cancel a pending or running job."""
        job_manager = get_job_manager()
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            return {"message": "Job already completed or failed", "job_id": job_id}
        job_manager.cancel_job(job_id)
        logger.info(f"Job {job_id} cancelled")
        return {"message": f"Job {job_id} cancelled"}

    @router.get("/", response_model=JobListResponse, summary="List jobs")
    async def list_jobs(
        job_type: Optional[str] = None, limit: int = 100, offset: int = 0
    ):
        """List all jobs (most recent first), optionally filtered by type."""
        job_manager = get_job_manager()
        all_jobs = job_manager.list_jobs(job_type=job_type)
        total = len(all_jobs)
        paginated = all_jobs[offset : offset + limit]
        return JobListResponse(
            jobs=[_job_to_status_response(j) for j in paginated],
            total=total,
        )

    return router
