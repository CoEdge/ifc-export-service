"""Convert intermediate mesh data to IFC geometry representations."""
import ifcopenshell

from app.ifc.geometry import create_triangulated_face_set, create_shape_representation


def mesh_to_ifc_shape(
    ifc: ifcopenshell.file,
    body_context,
    mesh_data: dict,
    source_units: str = "feet",
):
    """Convert a mesh_data dict to an IfcProductDefinitionShape.

    Args:
        ifc: The IFC file.
        body_context: IfcGeometricRepresentationSubContext (Body).
        mesh_data: Dict with ``positions`` and ``indices`` flat arrays.
        source_units: Source coordinate system units.

    Returns:
        IfcProductDefinitionShape entity.
    """
    face_set = create_triangulated_face_set(
        ifc,
        mesh_data["positions"],
        mesh_data["indices"],
        source_units,
    )
    shape_rep = create_shape_representation(ifc, body_context, face_set)
    return ifc.createIfcProductDefinitionShape(Representations=[shape_rep])
