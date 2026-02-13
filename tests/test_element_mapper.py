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


class TestGetPredefinedType:
    def test_floor_is_floor(self):
        assert get_predefined_type("floor") == "FLOOR"

    def test_unknown_returns_none(self):
        assert get_predefined_type("column") is None
