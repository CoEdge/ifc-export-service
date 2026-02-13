"""Map element type strings from the intermediate format to IFC4 entity classes."""
import logging
from typing import Optional

import ifcopenshell

from app.ifc.placement import create_local_placement
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
}


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
