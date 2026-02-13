"""
Jobs API Router for async IFC export tasks.

Provides endpoints for creating and managing background jobs
for IFC file generation.
"""

import asyncio
import base64
import io
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import IFCExportRequest
from app.services.ifc_builder import IFCBuilder
from app.services.job_manager import Job, JobStatus, get_job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

# In-memory store for generated IFC file bytes, keyed by job_id
_ifc_file_cache: Dict[str, bytes] = {}


# -- DSL input models (mirrors 3d-modeling-service schema) --------------------

class _Point2D(BaseModel):
    x: float
    y: float


class _BIMObject(BaseModel):
    id: Optional[str] = None
    type: str
    params: Dict[str, Any] = Field(default_factory=dict)
    position: Optional[_Point2D] = None
    floor_id: Optional[Any] = None


class DSLInput(BaseModel):
    """Minimal BIM DSL input model."""
    version: Optional[str] = "0.2.0"
    objects: List[_BIMObject]


# -- Response models ----------------------------------------------------------

class JobCreatedResponse(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    message: str = Field(..., description="Status message")
    poll_url: str = Field(..., description="URL to poll for job status")


class JobStatusResponse(BaseModel):
    id: str
    type: str
    status: JobStatus
    progress: int
    message: str
    metadata: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: List[JobStatusResponse]
    total: int


# -- Helpers ------------------------------------------------------------------

def _job_to_response(job: Job) -> JobStatusResponse:
    return JobStatusResponse(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        message=job.message,
        metadata=job.metadata,
        result=job.result,
        error=job.error,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


async def _build_ifc(request: IFCExportRequest, job_id: str) -> Dict[str, Any]:
    """Build IFC file in a thread pool and cache the result bytes."""
    job_manager = get_job_manager()

    job_manager.update_job(job_id, progress=10, message="Parsing request data")

    builder = IFCBuilder()

    job_manager.update_job(job_id, progress=30, message="Building IFC model")

    # Run the CPU-bound IFC build in a thread
    ifc_bytes = await asyncio.to_thread(builder.build, request)

    job_manager.update_job(job_id, progress=90, message="Finalizing IFC file")

    # Cache the bytes for download
    _ifc_file_cache[job_id] = ifc_bytes

    return {
        "file_size": len(ifc_bytes),
        "element_count": len(request.elements),
        "storey_count": len(request.storeys) if request.storeys else 0,
        "download_url": f"/api/v1/jobs/{job_id}/download",
    }


async def _build_ifc_from_dsl(dsl_input: DSLInput, job_id: str) -> Dict[str, Any]:
    """Fetch intermediate mesh from 3d-modeling-service, then build IFC."""
    job_manager = get_job_manager()

    job_manager.update_job(job_id, progress=5, message="Contacting 3d-modeling-service")

    modeling_url = f"{settings.MODELING_SERVICE_URL}/api/v1/jobs/ifc-mesh"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                modeling_url,
                json=dsl_input.model_dump(exclude_none=True),
            )
            resp.raise_for_status()
            intermediate = resp.json()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach 3d-modeling-service at {settings.MODELING_SERVICE_URL}"
        )
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"3d-modeling-service returned {exc.response.status_code}: "
            f"{exc.response.text[:500]}"
        )

    job_manager.update_job(job_id, progress=40, message="Received mesh data, building IFC model")

    ifc_request = IFCExportRequest(**intermediate)
    builder = IFCBuilder()

    ifc_bytes = await asyncio.to_thread(builder.build, ifc_request)

    job_manager.update_job(job_id, progress=90, message="Finalizing IFC file")

    _ifc_file_cache[job_id] = ifc_bytes

    return {
        "file_size": len(ifc_bytes),
        "element_count": len(ifc_request.elements),
        "storey_count": len(ifc_request.storeys) if ifc_request.storeys else 0,
        "download_url": f"/api/v1/jobs/{job_id}/download",
    }


# -- Job management endpoints ------------------------------------------------

@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get job status and result."""
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return _job_to_response(job)


@router.get("/{job_id}/result")
async def get_job_result(job_id: str):
    """Get job result metadata.

    Returns 202 if still processing, 200 with result if completed.
    """
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job is still {job.status.value}",
        )

    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=job.error or "Job failed",
        )

    return job.result


@router.get("/{job_id}/download")
async def download_ifc_file(job_id: str):
    """Download the generated IFC file.

    Only available after the job has completed successfully.
    """
    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job is still {job.status.value}",
        )

    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=job.error or "Job failed",
        )

    ifc_bytes = _ifc_file_cache.get(job_id)
    if not ifc_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IFC file no longer available (expired from cache)",
        )

    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="model.ifc"'},
    )


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job."""
    job_manager = get_job_manager()
    success = job_manager.cancel_job(job_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not found or cannot be cancelled",
        )

    # Clean up cached file if any
    _ifc_file_cache.pop(job_id, None)

    return {"message": f"Job {job_id} cancelled successfully"}


@router.get("/", response_model=JobListResponse)
async def list_jobs(job_type: Optional[str] = None, limit: int = 100):
    """List recent jobs."""
    job_manager = get_job_manager()
    jobs = job_manager.list_jobs(job_type=job_type, limit=limit)

    return JobListResponse(
        jobs=[_job_to_response(job) for job in jobs],
        total=len(jobs),
    )


# -- Job creation endpoints ---------------------------------------------------

@router.post("/convert", response_model=JobCreatedResponse)
async def create_convert_job(request: IFCExportRequest):
    """Create a job to convert intermediate mesh format to IFC4.

    Returns immediately with a job ID. Poll /api/v1/jobs/{job_id} for status.
    When completed, download the file at /api/v1/jobs/{job_id}/download.
    """
    job_manager = get_job_manager()

    job = job_manager.create_job(
        job_type="ifc-convert",
        metadata={
            "element_count": len(request.elements),
            "storey_count": len(request.storeys) if request.storeys else 0,
            "source_units": request.source_units,
        },
    )

    job_manager.start_background_job(
        job.id,
        _build_ifc,
        request,
        job.id,
    )

    return JobCreatedResponse(
        job_id=job.id,
        status=job.status,
        message="IFC conversion job created",
        poll_url=f"/api/v1/jobs/{job.id}",
    )


@router.post("/convert-from-dsl", response_model=JobCreatedResponse)
async def create_convert_dsl_job(request: DSLInput):
    """Create a job to convert BIM DSL to IFC4 via the 3d-modeling-service.

    Returns immediately with a job ID. Poll /api/v1/jobs/{job_id} for status.
    When completed, download the file at /api/v1/jobs/{job_id}/download.
    """
    job_manager = get_job_manager()

    job = job_manager.create_job(
        job_type="ifc-convert-dsl",
        metadata={
            "dsl_version": request.version,
            "object_count": len(request.objects),
        },
    )

    job_manager.start_background_job(
        job.id,
        _build_ifc_from_dsl,
        request,
        job.id,
    )

    return JobCreatedResponse(
        job_id=job.id,
        status=job.status,
        message="IFC conversion from DSL job created",
        poll_url=f"/api/v1/jobs/{job.id}",
    )
