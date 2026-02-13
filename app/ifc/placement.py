"""IFC placement helpers for IfcLocalPlacement and IfcAxis2Placement3D."""
import ifcopenshell


def create_axis2_placement_3d(
    ifc: ifcopenshell.file,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
):
    """Create an IfcAxis2Placement3D at the given coordinates.

    Uses default Z-up axis and X ref-direction.
    """
    location = ifc.createIfcCartesianPoint((x, y, z))
    return ifc.createIfcAxis2Placement3D(Location=location)


def create_local_placement(
    ifc: ifcopenshell.file,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    relative_to=None,
):
    """Create an IfcLocalPlacement at (x, y, z), optionally relative to another placement."""
    axis2 = create_axis2_placement_3d(ifc, x, y, z)
    return ifc.createIfcLocalPlacement(
        PlacementRelTo=relative_to,
        RelativePlacement=axis2,
    )
