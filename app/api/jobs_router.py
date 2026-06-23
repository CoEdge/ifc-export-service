"""
IFC Export Jobs API Router.

Service-specific job creation endpoints for IFC export tasks.
Generic job management endpoints (status, result, cancel, list) are
provided by the canonical factory in app.core.jobs_router.
"""

import asyncio
import io
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.core.job_manager import get_job_manager, JobStatus
from app.core.jobs_router import create_jobs_router, create_job_response
from app.models.schemas import IFCExportRequest, SteelExportRequest
from app.services.ifc_builder import IFCBuilder

logger = logging.getLogger(__name__)

# Create router with canonical job management endpoints
# (GET /{job_id}, GET /{job_id}/result, DELETE /{job_id}, GET /)
router = create_jobs_router(prefix="/api/v1/jobs", tags=["jobs"])

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


# -- IFC build helpers --------------------------------------------------------

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


async def _build_steel_ifc(request: SteelExportRequest, job_id: str) -> Dict[str, Any]:
    """Build a parametric steel IFC file in a thread pool and cache the bytes."""
    job_manager = get_job_manager()

    job_manager.update_job(job_id, progress=10, message="Parsing steel members")

    builder = IFCBuilder()

    job_manager.update_job(job_id, progress=30, message="Building steel IFC model")

    ifc_bytes = await asyncio.to_thread(builder.build_steel, request)

    job_manager.update_job(job_id, progress=90, message="Finalizing IFC file")

    _ifc_file_cache[job_id] = ifc_bytes

    return {
        "file_size": len(ifc_bytes),
        "element_count": len(request.members),
        "storey_count": len(request.storeys) if request.storeys else 0,
        "download_url": f"/api/v1/jobs/{job_id}/download",
    }


# -- IFC-specific endpoints ---------------------------------------------------

@router.get(
    "/{job_id}/download",
    summary="Download IFC file",
    description="Download the generated IFC file. Only available after the job has completed.",
)
async def download_ifc_file(job_id: str):
    """Download the generated IFC file."""
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


@router.post(
    "/convert",
    summary="Convert mesh to IFC",
    description="Create a job to convert intermediate mesh format to IFC4. "
    "Returns immediately with a job ID for polling.",
)
async def create_convert_job(request: IFCExportRequest):
    """Create a job to convert intermediate mesh format to IFC4."""
    job_manager = get_job_manager()

    job = job_manager.create_job(
        job_type="ifc-convert",
        metadata={
            "element_count": len(request.elements),
            "storey_count": len(request.storeys) if request.storeys else 0,
            "source_units": request.source_units,
        },
    )

    job_manager.start_background_job(job.id, _build_ifc, request, job.id)

    return create_job_response(job, "IFC conversion", prefix="/api/v1/jobs")


@router.post(
    "/convert-from-dsl",
    summary="Convert BIM DSL to IFC",
    description="Create a job to convert BIM DSL to IFC4 via the 3d-modeling-service. "
    "Returns immediately with a job ID for polling.",
)
async def create_convert_dsl_job(request: DSLInput):
    """Create a job to convert BIM DSL to IFC4 via 3d-modeling-service."""
    job_manager = get_job_manager()

    job = job_manager.create_job(
        job_type="ifc-convert-dsl",
        metadata={
            "dsl_version": request.version,
            "object_count": len(request.objects),
        },
    )

    job_manager.start_background_job(job.id, _build_ifc_from_dsl, request, job.id)

    return create_job_response(job, "IFC conversion from DSL", prefix="/api/v1/jobs")


@router.post(
    "/convert-steel",
    summary="Convert steel model to IFC",
    description="Create a job to convert a Steel Structure model to IFC4 "
    "(parametric IfcColumn/IfcBeam/IfcFooting). Returns immediately with a job ID.",
)
async def create_convert_steel_job(request: SteelExportRequest):
    """Create a job to convert a steel structural model to IFC4."""
    job_manager = get_job_manager()

    job = job_manager.create_job(
        job_type="ifc-convert-steel",
        metadata={
            "member_count": len(request.members),
            "storey_count": len(request.storeys) if request.storeys else 0,
            "source_units": request.source_units,
        },
    )

    job_manager.start_background_job(job.id, _build_steel_ifc, request, job.id)

    return create_job_response(job, "Steel IFC conversion", prefix="/api/v1/jobs")
