"""Map element metadata (groups/fields) to IfcPropertySet entities.

Handles the units and field types of the current ``bim_response_output`` schema:

    units  — ft, in, deg, ft², ft³, %, kips, plf, psf, ksi, kip-ft, sq ft, psi
    types  — text, number, dimension, boolean, coordinate, list, angle, area,
             volume, percentage, image

Geometric quantities (length/area/volume/angle) are converted to the file's SI
units (metre, m², m³, radian) and emitted as the matching IFC measure type.
Structural quantities (force/pressure/linear-force/moment) have no SI base unit
in the file, so they are emitted as ``IfcReal`` annotated with an
``IfcContextDependentUnit`` carrying the unit symbol — never rescaled.
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import ifcopenshell

from app.services.unit_converter import FEET_TO_METERS, INCH_TO_METERS

logger = logging.getLogger(__name__)

# Unit symbol → linear conversion factor to the file's SI base units.
_LENGTH_FACTORS: Dict[str, float] = {"ft": FEET_TO_METERS, "in": INCH_TO_METERS}
_AREA_FACTORS: Dict[str, float] = {"ft²": FEET_TO_METERS ** 2, "sq ft": FEET_TO_METERS ** 2}
_VOLUME_FACTORS: Dict[str, float] = {"ft³": FEET_TO_METERS ** 3}

# Structural units (force/pressure/linear-force/moment). These have no SI base
# unit in the file, so the numeric value is preserved as-is and annotated with a
# USERDEFINED IfcContextDependentUnit carrying the symbol. (LINEARFORCEUNIT /
# TORQUEUNIT are not IfcUnitEnum members, so USERDEFINED is used for all.)
_STRUCTURAL_UNITS: frozenset = frozenset({"kips", "plf", "psf", "ksi", "kip-ft", "psi"})


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


def _context_dependent_unit(ifc: ifcopenshell.file, symbol: str):
    """Find or create an IfcContextDependentUnit for a structural unit symbol.

    Returns ``None`` if creation fails so the property is still emitted (unitless).
    """
    for existing in ifc.by_type("IfcContextDependentUnit"):
        if existing.Name == symbol:
            return existing
    try:
        dims = ifc.createIfcDimensionalExponents(0, 0, 0, 0, 0, 0, 0)
        return ifc.createIfcContextDependentUnit(
            Dimensions=dims,
            UnitType="USERDEFINED",
            Name=symbol,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not create context-dependent unit '%s': %s", symbol, exc)
        return None


def _nominal_and_unit(
    ifc: ifcopenshell.file,
    value: Any,
    field_type: str,
    unit: Optional[str],
) -> Optional[Tuple[Any, Any]]:
    """Resolve a field value+type+unit to ``(NominalValue, Unit)`` for an
    IfcPropertySingleValue, applying SI conversion for geometric quantities.

    Returns ``None`` when the field should be skipped (e.g. images).
    """
    # Non-numeric kinds first.
    if field_type == "boolean":
        return ifc.createIfcBoolean(bool(value)), None
    if field_type == "image":
        return None  # don't embed image data as a property
    if field_type == "list":
        text = ", ".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)
        return ifc.createIfcLabel(text), None
    if field_type in ("text", "coordinate"):
        return ifc.createIfcLabel(str(value)), None

    # Numeric kinds: dimension, number, area, volume, angle, percentage.
    try:
        num = float(value)
    except (TypeError, ValueError):
        # Unexpected non-numeric value for a numeric type \u2014 keep it as text.
        return ifc.createIfcLabel(str(value)), None

    if unit in _LENGTH_FACTORS:
        return ifc.createIfcLengthMeasure(num * _LENGTH_FACTORS[unit]), None
    if unit in _AREA_FACTORS or field_type == "area":
        factor = _AREA_FACTORS.get(unit, 1.0)
        return ifc.createIfcAreaMeasure(num * factor), None
    if unit in _VOLUME_FACTORS or field_type == "volume":
        factor = _VOLUME_FACTORS.get(unit, 1.0)
        return ifc.createIfcVolumeMeasure(num * factor), None
    if unit == "deg" or field_type == "angle":
        # File angle unit is radian.
        return ifc.createIfcPlaneAngleMeasure(math.radians(num)), None
    if unit == "%" or field_type == "percentage":
        return ifc.createIfcRatioMeasure(num), None
    if unit in _STRUCTURAL_UNITS:
        # Force/pressure/moment \u2014 no SI base unit in the file; keep value as-is
        # and annotate with a context-dependent unit.
        return ifc.createIfcReal(num), _context_dependent_unit(ifc, unit)

    # Plain unitless number (counts, DCRs, KL/r, etc.).
    return ifc.createIfcReal(num), None


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
        resolved = _nominal_and_unit(ifc, value, field_type, unit)
        if resolved is None:
            return None
        nominal, unit_obj = resolved
        return ifc.createIfcPropertySingleValue(
            Name=label,
            NominalValue=nominal,
            Unit=unit_obj,
        )
    except Exception as exc:
        logger.warning("Could not create IFC property for field '%s': %s", label, exc)
        return None
