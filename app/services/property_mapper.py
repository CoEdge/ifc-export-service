"""Map element metadata (groups/fields) to IfcPropertySet entities."""
import logging
from typing import Any, Dict, List, Optional

import ifcopenshell

from app.services.unit_converter import FEET_TO_METERS

logger = logging.getLogger(__name__)


def create_property_sets(
    ifc: ifcopenshell.file,
    element,
    properties_data: Optional[Dict[str, Any]],
    source_units: str = "feet",
):
    """Create IfcPropertySet entities from intermediate element properties and
    attach them to the IFC element via IfcRelDefinesByProperties.

    The properties_data structure mirrors the output of ``_build_element_metadata()``
    from the 3d-modeling-service which produces::

        {
            "element_id": "...",
            "element_type": "...",
            "groups": [
                {
                    "id": "identity",
                    "label": "Identity",
                    "fields": [
                        {"id": "id", "label": "ID", "value": "wall_1", "type": "text"},
                        {"id": "height", "label": "Height", "value": 10.0, "type": "dimension", "unit": "ft"},
                        ...
                    ]
                }
            ]
        }

    Args:
        ifc: The IFC file being constructed.
        element: The IFC product entity to attach properties to.
        properties_data: Metadata dict (may be ``None``).
        source_units: Source unit system for dimension conversion.
    """
    if not properties_data:
        return

    groups: List[dict] = []
    if isinstance(properties_data, dict):
        groups = properties_data.get("groups", [])
    elif isinstance(properties_data, list):
        groups = properties_data

    for group in groups:
        group_label = group.get("label", "Properties")
        fields = group.get("fields", [])
        if not fields:
            continue

        ifc_properties = []
        for field in fields:
            prop = _field_to_ifc_property(ifc, field, source_units)
            if prop is not None:
                ifc_properties.append(prop)

        if not ifc_properties:
            continue

        pset_name = f"Pset_{group_label.replace(' ', '')}"
        pset = ifc.createIfcPropertySet(
            GlobalId=ifcopenshell.guid.new(),
            Name=pset_name,
            HasProperties=ifc_properties,
        )
        ifc.createIfcRelDefinesByProperties(
            GlobalId=ifcopenshell.guid.new(),
            RelatingPropertyDefinition=pset,
            RelatedObjects=[element],
        )


def _field_to_ifc_property(
    ifc: ifcopenshell.file,
    field: dict,
    source_units: str,
):
    """Convert a single metadata field to an IfcPropertySingleValue."""
    label = field.get("label", field.get("id", ""))
    value = field.get("value")
    field_type = field.get("type", "text")
    unit = field.get("unit")

    if value is None:
        return None

    try:
        if field_type in ("dimension", "number"):
            float_val = float(value)
            # Convert length dimensions from feet to metres
            if unit == "ft" and source_units == "feet":
                float_val = float_val * FEET_TO_METERS
            elif unit == "ft\u00b2" and source_units == "feet":
                float_val = float_val * (FEET_TO_METERS ** 2)
            return ifc.createIfcPropertySingleValue(
                Name=label,
                NominalValue=ifc.createIfcReal(float_val),
            )
        elif field_type == "boolean":
            return ifc.createIfcPropertySingleValue(
                Name=label,
                NominalValue=ifc.createIfcBoolean(bool(value)),
            )
        elif field_type == "angle":
            return ifc.createIfcPropertySingleValue(
                Name=label,
                NominalValue=ifc.createIfcReal(float(value)),
            )
        else:
            # text, coordinate, list, percentage, etc.
            return ifc.createIfcPropertySingleValue(
                Name=label,
                NominalValue=ifc.createIfcLabel(str(value)),
            )
    except Exception as exc:
        logger.warning("Could not create IFC property for field '%s': %s", label, exc)
        return None
