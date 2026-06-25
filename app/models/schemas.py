from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class MeshData(BaseModel):
    """Tessellated mesh data for a single element."""
    positions: List[float] = Field(
        ..., description="Flat vertex positions [x0,y0,z0, x1,y1,z1, ...] in source units"
    )
    normals: Optional[List[float]] = Field(
        None, description="Flat per-vertex normals [nx0,ny0,nz0, ...]"
    )
    indices: List[int] = Field(
        ..., description="Flat triangle indices [i0,i1,i2, ...] (0-based)"
    )


class ElementData(BaseModel):
    """A single BIM element with mesh and metadata."""
    id: str
    type: str = Field(..., description="Element type: wall_segment, wall_junction, floor, foundation, roof, door, window")
    floor_id: Optional[str] = Field(None, description="Reference to storey for spatial grouping")
    mesh: MeshData
    properties: Optional[Dict[str, Any]] = Field(None, description="Element metadata (groups/fields)")


class StoreyData(BaseModel):
    """Building storey definition."""
    id: str
    name: Optional[str] = None
    elevation: float = Field(..., description="Storey elevation in source units")


class ProjectData(BaseModel):
    """Project-level metadata."""
    name: str = "BIM Model"
    description: Optional[str] = None
    author: Optional[str] = None
    organization: Optional[str] = None


class SiteData(BaseModel):
    """Site-level metadata."""
    name: str = "Default Site"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class BuildingData(BaseModel):
    """Building-level metadata."""
    name: str = "Default Building"


class IFCExportRequest(BaseModel):
    """Request body for the /convert endpoint."""
    project: Optional[ProjectData] = Field(default_factory=ProjectData)
    site: Optional[SiteData] = Field(default_factory=SiteData)
    building: Optional[BuildingData] = Field(default_factory=BuildingData)
    source_units: str = Field("feet", description="Source coordinate units: feet or meters")
    coordinate_system: str = Field("z_up", description="Coordinate system orientation")
    storeys: Optional[List[StoreyData]] = Field(default_factory=list)
    elements: List[ElementData]


class SteelFootingData(BaseModel):
    """Spread-footing dimensions for a foundation pad (source units)."""
    width_ft: float
    depth_ft: float
    thickness_ft: float


class SteelMemberData(BaseModel):
    """A single steel member for parametric IFC export.

    Carries the section ``designation`` (→ I-shape profile), ``length`` and a
    3×4 row-major ``[up|lat|dir|pos]`` transform so the exporter can build an
    ``IfcExtrudedAreaSolid``. Footing dims are given for foundation pads. When
    parametric data is missing the exporter falls back to ``mesh`` (if present)
    or a geometry-less proxy.
    """
    id: str
    kind: str = Field(
        ...,
        description="steel_w_column | steel_w_beam | steel_transfer_girder | "
        "steel_joist | steel_column | steel_foundation_pad | steel_connection",
    )
    designation: Optional[str] = Field(None, description="AISC W-shape designation, e.g. W24x68")
    length_ft: Optional[float] = Field(None, description="Member length (source units)")
    transform: Optional[List[float]] = Field(
        None, description="3x4 row-major [up|lat|dir|pos] local->world transform"
    )
    floor_id: Optional[str] = Field(None, description="Storey id for spatial grouping")
    footing: Optional[SteelFootingData] = Field(None, description="Footing dims for foundation pads")
    steel_grade: Optional[str] = Field(None, description="Material grade, e.g. A992")
    mesh: Optional[MeshData] = Field(None, description="Optional fallback mesh geometry")
    properties: Optional[Dict[str, Any]] = Field(None, description="Element metadata (groups/fields)")


class SteelExportRequest(BaseModel):
    """Request body for the /convert-steel endpoint."""
    project: Optional[ProjectData] = Field(default_factory=ProjectData)
    site: Optional[SiteData] = Field(default_factory=SiteData)
    building: Optional[BuildingData] = Field(default_factory=BuildingData)
    source_units: str = Field("feet", description="Source coordinate units: feet or meters")
    coordinate_system: str = Field("z_up", description="Coordinate system orientation")
    storeys: Optional[List[StoreyData]] = Field(default_factory=list)
    members: List[SteelMemberData]


class IFCExportResponse(BaseModel):
    """Response metadata (returned alongside the file when requested as JSON)."""
    success: bool
    file_size: Optional[int] = None
    element_count: Optional[int] = None
    storey_count: Optional[int] = None
    error: Optional[str] = None
