import pytest
from app.services.element_mapper import get_ifc_class, get_predefined_type


class TestGetIfcClass:
    def test_wall_segment(self):
        assert get_ifc_class("wall_segment") == "IfcWall"

    def test_wall_junction(self):
        assert get_ifc_class("wall_junction") == "IfcWall"

    def test_floor(self):
        assert get_ifc_class("floor") == "IfcSlab"

    def test_foundation(self):
        assert get_ifc_class("foundation") == "IfcFooting"

    def test_roof(self):
        assert get_ifc_class("roof") == "IfcRoof"

    def test_door(self):
        assert get_ifc_class("door") == "IfcDoor"

    def test_window(self):
        assert get_ifc_class("window") == "IfcWindow"

    def test_unknown_type_falls_back(self):
        assert get_ifc_class("column") == "IfcBuildingElementProxy"

    @pytest.mark.parametrize("kind,expected", [
        ("steel_w_column", "IfcColumn"),
        ("steel_column", "IfcColumn"),
        ("steel_w_beam", "IfcBeam"),
        ("steel_transfer_girder", "IfcBeam"),
        ("steel_joist", "IfcBeam"),
        ("steel_foundation_pad", "IfcFooting"),
        ("steel_connection", "IfcPlate"),
    ])
    def test_steel_kinds(self, kind, expected):
        assert get_ifc_class(kind) == expected


class TestGetPredefinedType:
    def test_floor_is_floor(self):
        assert get_predefined_type("floor") == "FLOOR"

    def test_unknown_returns_none(self):
        assert get_predefined_type("column") is None

    @pytest.mark.parametrize("kind,expected", [
        ("steel_w_column", "COLUMN"),
        ("steel_w_beam", "BEAM"),
        ("steel_transfer_girder", "BEAM"),
        ("steel_joist", "JOIST"),
        ("steel_foundation_pad", "PAD_FOOTING"),
    ])
    def test_steel_predefined(self, kind, expected):
        assert get_predefined_type(kind) == expected
