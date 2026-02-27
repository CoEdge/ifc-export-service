import io
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import IFCExportRequest
from app.services.ifc_builder import IFCBuilder

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync-conversion"])


@router.post(
    "/convert",
    summary="Synchronous mesh-to-IFC conversion",
    description="Convert intermediate mesh format to an IFC4 file. "
    "Returns the IFC file directly as a streaming download. "
    "For large models, prefer the async job-based endpoint at /api/v1/jobs/convert.",
)
async def convert_to_ifc(request: IFCExportRequest):
    """Convert intermediate mesh format to an IFC4 file."""
    builder = IFCBuilder()
    ifc_bytes = builder.build(request)

    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="model.ifc"'},
    )


# -- Convenience endpoint: accept raw BIM DSL ---------------------------------

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
    """Minimal BIM DSL input model (mirrors 3d-modeling-service schema)."""
    version: Optional[str] = "0.2.0"
    objects: List[_BIMObject]


@router.post(
    "/convert-from-dsl",
    summary="Synchronous BIM DSL-to-IFC conversion",
    description="Convert BIM DSL to IFC4 via the 3d-modeling-service. "
    "Forwards DSL to the 3d-modeling-service for mesh generation, then produces IFC4. "
    "For large models, prefer the async job-based endpoint at /api/v1/jobs/convert-from-dsl.",
)
async def convert_dsl_to_ifc(request: DSLInput):
    """Convert BIM DSL to IFC4 via the 3d-modeling-service.

    This convenience endpoint accepts raw BIM DSL JSON, forwards it to the
    3d-modeling-service's ``/api/v1/jobs/ifc-mesh`` endpoint to obtain the
    intermediate mesh format, then produces the IFC4 file.
    """
    modeling_url = f"{settings.MODELING_SERVICE_URL}/api/v1/jobs/ifc-mesh"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                modeling_url,
                json=request.model_dump(exclude_none=True),
            )
            resp.raise_for_status()
            intermediate = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach 3d-modeling-service at {settings.MODELING_SERVICE_URL}",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"3d-modeling-service returned {exc.response.status_code}: {exc.response.text[:500]}",
        )

    ifc_request = IFCExportRequest(**intermediate)
    builder = IFCBuilder()
    ifc_bytes = builder.build(ifc_request)

    return StreamingResponse(
        io.BytesIO(ifc_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="model.ifc"'},
    )


@router.get("/health", summary="V1 health check", tags=["health"])
def health_v1():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
