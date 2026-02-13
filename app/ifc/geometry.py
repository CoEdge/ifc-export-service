"""IFC geometry helpers for creating IfcTriangulatedFaceSet representations."""
import ifcopenshell

from app.services.unit_converter import convert_positions


def create_triangulated_face_set(
    ifc: ifcopenshell.file,
    positions_flat: list[float],
    indices_flat: list[int],
    source_units: str = "feet",
):
    """Create an IfcTriangulatedFaceSet from flat mesh arrays.

    Args:
        ifc: The IFC file being constructed.
        positions_flat: Flat vertex positions [x0,y0,z0, x1,y1,z1, ...] in source_units.
        indices_flat: Flat 0-based triangle indices [i0,i1,i2, ...].
        source_units: Coordinate unit system ("feet" or "meters").

    Returns:
        The IfcTriangulatedFaceSet entity.
    """
    # Convert to metres
    positions_m = convert_positions(positions_flat, source_units)

    # Group into coordinate tuples for IfcCartesianPointList3D
    coord_list = []
    for i in range(0, len(positions_m), 3):
        coord_list.append((positions_m[i], positions_m[i + 1], positions_m[i + 2]))

    # Group indices into triangle tuples (IFC uses 1-based indexing)
    triangles = []
    for i in range(0, len(indices_flat), 3):
        triangles.append((
            indices_flat[i] + 1,
            indices_flat[i + 1] + 1,
            indices_flat[i + 2] + 1,
        ))

    point_list = ifc.createIfcCartesianPointList3D(CoordList=coord_list)

    face_set = ifc.createIfcTriangulatedFaceSet(
        Coordinates=point_list,
        CoordIndex=triangles,
        Closed=False,
    )

    return face_set


def create_shape_representation(
    ifc: ifcopenshell.file,
    body_context,
    face_set,
):
    """Wrap an IfcTriangulatedFaceSet in an IfcShapeRepresentation.

    Args:
        ifc: The IFC file being constructed.
        body_context: IfcGeometricRepresentationSubContext for Body.
        face_set: The IfcTriangulatedFaceSet to wrap.

    Returns:
        The IfcShapeRepresentation entity.
    """
    return ifc.createIfcShapeRepresentation(
        ContextOfItems=body_context,
        RepresentationIdentifier="Body",
        RepresentationType="Tessellation",
        Items=[face_set],
    )
