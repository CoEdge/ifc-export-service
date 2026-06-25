"""Unit conversion utilities for IFC export.

The 3d-modeling-service uses feet and Z-up coordinates.
IFC4 conventionally uses metres as the base length unit.
"""

FEET_TO_METERS: float = 0.3048
INCH_TO_METERS: float = 0.0254


def ft_to_m(value: float) -> float:
    """Convert a single value from feet to metres."""
    return value * FEET_TO_METERS


def convert_positions(positions_flat: list[float], source_units: str = "feet") -> list[float]:
    """Convert a flat positions array from source units to metres.

    Args:
        positions_flat: Flat list [x0,y0,z0, x1,y1,z1, ...]
        source_units: "feet" or "meters"

    Returns:
        Converted flat list in metres.
    """
    if source_units == "meters":
        return positions_flat
    return [v * FEET_TO_METERS for v in positions_flat]


def convert_elevation(elevation: float, source_units: str = "feet") -> float:
    """Convert an elevation value from source units to metres."""
    if source_units == "meters":
        return elevation
    return elevation * FEET_TO_METERS


def convert_dimension(dimension: float, source_units: str = "feet") -> float:
    """Convert a dimension (length, width, thickness, etc.) from source units to metres."""
    if source_units == "meters":
        return dimension
    return dimension * FEET_TO_METERS
