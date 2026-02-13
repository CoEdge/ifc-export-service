import json
import tempfile
from pathlib import Path

import ifcopenshell
import pytest

from app.models.schemas import IFCExportRequest
from app.services.ifc_builder import IFCBuilder
from app.services.unit_converter import FEET_TO_METERS


class TestIFCBuilderSimpleWall:
    """Test IFC builder with simple_wall.json fixture."""

    @pytest.fixture
    def ifc_bytes(self, simple_wall_data):
        request = IFCExportRequest(**simple_wall_data)
        builder = IFCBuilder()
        return builder.build(request)

    @pytest.fixture
    def ifc_file(self, ifc_bytes):
        """Write IFC bytes to temp file and open with ifcopenshell."""
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            f.write(ifc_bytes)
            tmp_path = f.name
        ifc = ifcopenshell.open(tmp_path)
        yield ifc
        Path(tmp_path).unlink(missing_ok=True)

    def test_produces_bytes(self, ifc_bytes):
        assert isinstance(ifc_bytes, bytes)
        assert len(ifc_bytes) > 0

    def test_valid_ifc4(self, ifc_file):
        assert ifc_file.schema == "IFC4"

    def test_has_project(self, ifc_file):
        projects = ifc_file.by_type("IfcProject")
        assert len(projects) == 1
        assert projects[0].Name == "Test - Simple Wall"

    def test_has_site(self, ifc_file):
        assert len(ifc_file.by_type("IfcSite")) == 1

    def test_has_building(self, ifc_file):
        assert len(ifc_file.by_type("IfcBuilding")) == 1

    def test_has_storey(self, ifc_file):
        storeys = ifc_file.by_type("IfcBuildingStorey")
        assert len(storeys) == 1
        assert storeys[0].Name == "Ground Floor"
        assert storeys[0].Elevation == pytest.approx(1.0 * FEET_TO_METERS)

    def test_has_wall(self, ifc_file):
        walls = ifc_file.by_type("IfcWall")
        assert len(walls) == 1
        assert walls[0].Name == "wall_1"

    def test_has_triangulated_face_set(self, ifc_file):
        face_sets = ifc_file.by_type("IfcTriangulatedFaceSet")
        assert len(face_sets) == 1
        assert len(face_sets[0].Coordinates.CoordList) == 8
        assert len(face_sets[0].CoordIndex) == 12

    def test_spatial_containment(self, ifc_file):
        """Verify IfcRelContainedInSpatialStructure connects wall to storey."""
        rels = ifc_file.by_type("IfcRelContainedInSpatialStructure")
        assert len(rels) >= 1
        # At least one rel should contain the wall
        all_elements = []
        for rel in rels:
            all_elements.extend(rel.RelatedElements)
        wall_names = [e.Name for e in all_elements if e.is_a("IfcWall")]
        assert "wall_1" in wall_names

    def test_has_property_set(self, ifc_file):
        """Verify metadata was converted to IfcPropertySet."""
        psets = ifc_file.by_type("IfcPropertySet")
        assert len(psets) >= 1
        pset_names = [p.Name for p in psets]
        assert "Pset_Dimensions" in pset_names

    def test_hierarchy_chain(self, ifc_file):
        """Verify IfcRelAggregates connects Project -> Site -> Building -> Storey."""
        agg_rels = ifc_file.by_type("IfcRelAggregates")
        # Should have at least 3: Project->Site, Site->Building, Building->Storey
        assert len(agg_rels) >= 3

    def test_units_are_metres(self, ifc_file):
        """Verify the IFC file declares metres as the length unit."""
        unit_assignments = ifc_file.by_type("IfcUnitAssignment")
        assert len(unit_assignments) == 1
        units = unit_assignments[0].Units
        length_units = [u for u in units if u.UnitType == "LENGTHUNIT"]
        assert len(length_units) == 1
        assert length_units[0].Name == "METRE"


class TestIFCBuilderHouseModel:
    """Test IFC builder with a multi-element house model."""

    @pytest.fixture
    def ifc_file(self, house_model_data):
        request = IFCExportRequest(**house_model_data)
        builder = IFCBuilder()
        ifc_bytes = builder.build(request)
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            f.write(ifc_bytes)
            tmp_path = f.name
        ifc = ifcopenshell.open(tmp_path)
        yield ifc
        Path(tmp_path).unlink(missing_ok=True)

    def test_valid_ifc4(self, ifc_file):
        assert ifc_file.schema == "IFC4"

    def test_element_counts(self, ifc_file):
        assert len(ifc_file.by_type("IfcWall")) == 2  # wall_south + wall_east
        assert len(ifc_file.by_type("IfcSlab")) == 1  # floor_1
        assert len(ifc_file.by_type("IfcFooting")) == 1  # foundation_1
        assert len(ifc_file.by_type("IfcDoor")) == 1  # door_1
        assert len(ifc_file.by_type("IfcRoof")) == 1  # roof_1

    def test_storey_count(self, ifc_file):
        storeys = ifc_file.by_type("IfcBuildingStorey")
        assert len(storeys) == 2

    def test_face_set_count(self, ifc_file):
        face_sets = ifc_file.by_type("IfcTriangulatedFaceSet")
        assert len(face_sets) == 6  # One per element

    def test_all_indices_valid(self, ifc_file):
        """Verify all CoordIndex values are within the valid range."""
        for face_set in ifc_file.by_type("IfcTriangulatedFaceSet"):
            num_verts = len(face_set.Coordinates.CoordList)
            for tri in face_set.CoordIndex:
                for idx in tri:
                    assert 1 <= idx <= num_verts, (
                        f"Index {idx} out of range [1, {num_verts}]"
                    )
