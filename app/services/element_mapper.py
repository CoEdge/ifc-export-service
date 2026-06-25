"""Map element type strings from the intermediate format to IFC4 entity classes."""
import logging
from typing import Optional

import ifcopenshell

from app.ifc import steel_geometry
from app.ifc.placement import create_local_placement
from app.ifc.profiles import get_profile
from app.services.mesh_converter import mesh_to_ifc_shape

logger = logging.getLogger(__name__)

# Mapping of intermediate element type -> IFC entity class name
ELEMENT_TYPE_TO_IFC: dict[str, str] = {
    "wall_segment": "IfcWall",
    "wall_junction": "IfcWall",
    "floor": "IfcSlab",
    "foundation": "IfcFooting",
    "roof": "IfcRoof",
    "door": "IfcDoor",
    "window": "IfcWindow",
    # Steel structural members (kind / element_type from the steel pipeline).
    "steel_w_column": "IfcColumn",
    "steel_column": "IfcColumn",
    "steel_w_beam": "IfcBeam",
    "steel_beam": "IfcBeam",
    "steel_transfer_girder": "IfcBeam",
    "steel_joist": "IfcBeam",
    "steel_foundation_pad": "IfcFooting",
    "steel_connection": "IfcPlate",
}

# Optional predefined types for more specific IFC classification
ELEMENT_PREDEFINED_TYPE: dict[str, str] = {
    "wall_segment": "STANDARD",
    "wall_junction": "STANDARD",
    "floor": "FLOOR",
    "foundation": "STRIP_FOOTING",
    "roof": "GABLE_ROOF",
    "door": "DOOR",
    "window": "WINDOW",
    "steel_w_column": "COLUMN",
    "steel_column": "COLUMN",
    "steel_w_beam": "BEAM",
    "steel_beam": "BEAM",
    "steel_transfer_girder": "BEAM",
    "steel_joist": "JOIST",
    "steel_foundation_pad": "PAD_FOOTING",
}

# Steel kinds treated as concrete footings (rectangular extrusion).
_STEEL_FOOTING_KINDS = frozenset({"steel_foundation_pad"})


def get_ifc_class(element_type: str) -> str:
    """Return the IFC entity class name for a given element type string."""
    return ELEMENT_TYPE_TO_IFC.get(element_type, "IfcBuildingElementProxy")


def get_predefined_type(element_type: str) -> Optional[str]:
    """Return the IFC predefined type for a given element type string."""
    return ELEMENT_PREDEFINED_TYPE.get(element_type)


def create_ifc_element(
    ifc: ifcopenshell.file,
    element_data: dict,
    body_context,
    source_units: str = "feet",
):
    """Create an IFC building element from intermediate element data.

    Args:
        ifc: The IFC file being constructed.
        element_data: Dict with ``id``, ``type``, ``mesh``, etc.
        body_context: IfcGeometricRepresentationSubContext (Body).
        source_units: Coordinate unit system.

    Returns:
        The created IFC entity (IfcWall, IfcSlab, etc.).
    """
    element_type = element_data["type"]
    ifc_class = get_ifc_class(element_type)

    # Build geometry
    product_shape = mesh_to_ifc_shape(
        ifc, body_context, element_data["mesh"], source_units,
    )

    # Placement at world origin (geometry already contains absolute coordinates)
    placement = create_local_placement(ifc)

    # Create the entity
    kwargs = dict(
        GlobalId=ifcopenshell.guid.new(),
        Name=element_data.get("id", "Unnamed"),
        ObjectPlacement=placement,
        Representation=product_shape,
    )

    predefined = get_predefined_type(element_type)
    if predefined:
        kwargs["PredefinedType"] = predefined

    element = ifc.create_entity(ifc_class, **kwargs)
    logger.debug("Created %s '%s'", ifc_class, element_data.get("id"))
    return element


def create_ifc_steel_element(
    ifc: ifcopenshell.file,
    member: dict,
    body_context,
    source_units: str = "feet",
):
    """Create a parametric IFC steel element from a steel member dict.

    Member dict fields::

        {
          "id": str,
          "kind": "steel_w_column" | "steel_w_beam" | "steel_transfer_girder"
                  | "steel_joist" | "steel_column" | "steel_foundation_pad" | ...,
          "designation": "W24x68",      # for I-shape members
          "length_ft": 30.5,            # member length
          "transform": [12 floats],     # 3x4 row-major [up|lat|dir|pos]
          "footing": {"width_ft", "depth_ft", "thickness_ft"},  # for pads
          "steel_grade": "A992",        # optional
          "mesh": {...},                # optional fallback geometry
          "properties": {...},          # element metadata (groups/fields)
        }

    Emits IfcColumn / IfcBeam / IfcFooting with an extruded swept solid. Falls
    back to an IfcBuildingElementProxy (mesh if provided, else geometry-less)
    when the section/length/transform needed for parametric geometry is missing.
    """
    kind = member.get("kind") or member.get("type") or ""
    name = member.get("id", "Unnamed")
    designation = member.get("designation")
    transform = member.get("transform")
    footing = member.get("footing")

    ifc_class = get_ifc_class(kind)
    predefined = get_predefined_type(kind)
    representation = None
    placement = None
    material_name = None

    try:
        if kind in _STEEL_FOOTING_KINDS and footing:
            solid = steel_geometry.box_extrusion(
                ifc, footing["width_ft"], footing["depth_ft"],
                footing["thickness_ft"], source_units,
            )
            representation = steel_geometry.swept_representation(ifc, body_context, solid)
            placement = (
                steel_geometry.placement_from_transform(ifc, transform, source_units)
                if transform else create_local_placement(ifc)
            )
            material_name = "Concrete"
        else:
            dims = get_profile(designation)
            length_ft = member.get("length_ft")
            if dims and length_ft and transform:
                solid = steel_geometry.ishape_extrusion(
                    ifc, dims, float(length_ft), source_units, name=designation,
                )
                representation = steel_geometry.swept_representation(ifc, body_context, solid)
                placement = steel_geometry.placement_from_transform(ifc, transform, source_units)
                material_name = f"Steel - {member.get('steel_grade', 'A992')}"
    except Exception as exc:
        logger.warning("Parametric steel geometry failed for '%s' (%s): %s", name, kind, exc)
        representation = None

    if representation is None:
        # Fallback: proxy with mesh geometry if available, else geometry-less.
        ifc_class = "IfcBuildingElementProxy"
        predefined = None
        material_name = None
        if member.get("mesh"):
            representation = mesh_to_ifc_shape(ifc, body_context, member["mesh"], source_units)
        placement = create_local_placement(ifc)
        logger.info(
            "Steel member '%s' (%s, designation=%s) fell back to proxy",
            name, kind, designation,
        )

    kwargs = dict(
        GlobalId=ifcopenshell.guid.new(),
        Name=name,
        ObjectPlacement=placement,
    )
    if representation is not None:
        kwargs["Representation"] = representation
    if predefined:
        kwargs["PredefinedType"] = predefined

    element = ifc.create_entity(ifc_class, **kwargs)

    if material_name:
        steel_geometry.associate_material(
            ifc, element, steel_geometry.get_material(ifc, material_name)
        )

    logger.debug("Created steel %s '%s' (%s)", ifc_class, name, designation)
    return element
