import pytest
import ifcopenshell

from app.ifc.geometry import create_triangulated_face_set, create_shape_representation
from app.ifc.templates import create_ifc4_file
from app.services.unit_converter import FEET_TO_METERS


# Simple cube mesh: 8 vertices, 12 triangles
CUBE_POSITIONS = [
    0.0, 0.0, 0.0,  # v0
    1.0, 0.0, 0.0,  # v1
    1.0, 1.0, 0.0,  # v2
    0.0, 1.0, 0.0,  # v3
    0.0, 0.0, 1.0,  # v4
    1.0, 0.0, 1.0,  # v5
    1.0, 1.0, 1.0,  # v6
    0.0, 1.0, 1.0,  # v7
]

CUBE_INDICES = [
    # bottom
    0, 2, 1, 0, 3, 2,
    # top
    4, 5, 6, 4, 6, 7,
    # front
    0, 1, 5, 0, 5, 4,
    # right
    1, 2, 6, 1, 6, 5,
    # back
    2, 3, 7, 2, 7, 6,
    # left
    3, 0, 4, 3, 4, 7,
]


class TestCreateTriangulatedFaceSet:
    def test_vertex_count(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        coord_list = face_set.Coordinates.CoordList
        assert len(coord_list) == 8  # 8 vertices

    def test_triangle_count(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        assert len(face_set.CoordIndex) == 12  # 12 triangles

    def test_one_based_indices(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        for tri in face_set.CoordIndex:
            for idx in tri:
                assert idx >= 1, f"IFC indices must be 1-based, got {idx}"

    def test_index_range(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        num_vertices = len(face_set.Coordinates.CoordList)
        for tri in face_set.CoordIndex:
            for idx in tri:
                assert idx <= num_vertices, f"Index {idx} exceeds vertex count {num_vertices}"

    def test_unit_conversion(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        # First vertex (0,0,0) stays (0,0,0)
        assert face_set.Coordinates.CoordList[0] == pytest.approx((0.0, 0.0, 0.0))
        # Second vertex (1,0,0) becomes (0.3048, 0, 0)
        assert face_set.Coordinates.CoordList[1][0] == pytest.approx(FEET_TO_METERS)

    def test_meters_passthrough(self):
        ifc, _, _ = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "meters")
        # Second vertex (1,0,0) stays (1, 0, 0)
        assert face_set.Coordinates.CoordList[1][0] == pytest.approx(1.0)


class TestCreateShapeRepresentation:
    def test_representation_type(self):
        ifc, _, body_context = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        shape_rep = create_shape_representation(ifc, body_context, face_set)
        assert shape_rep.RepresentationType == "Tessellation"

    def test_representation_identifier(self):
        ifc, _, body_context = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        shape_rep = create_shape_representation(ifc, body_context, face_set)
        assert shape_rep.RepresentationIdentifier == "Body"

    def test_items_contain_face_set(self):
        ifc, _, body_context = create_ifc4_file()
        face_set = create_triangulated_face_set(ifc, CUBE_POSITIONS, CUBE_INDICES, "feet")
        shape_rep = create_shape_representation(ifc, body_context, face_set)
        assert len(shape_rep.Items) == 1
        assert shape_rep.Items[0] == face_set
