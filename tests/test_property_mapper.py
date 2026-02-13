import ifcopenshell
import pytest

from app.ifc.templates import create_ifc4_file
from app.services.property_mapper import create_property_sets


@pytest.fixture
def ifc_with_wall():
    """Create an IFC file with a single IfcWall for property attachment tests."""
    ifc, project, body_context = create_ifc4_file()
    wall = ifc.createIfcWall(
        GlobalId=ifcopenshell.guid.new(),
        Name="test_wall",
    )
    return ifc, wall


class TestPropertyMapper:
    def test_creates_property_set(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        properties = {
            "groups": [
                {
                    "label": "Dimensions",
                    "fields": [
                        {"label": "Height", "value": 10.0, "type": "dimension", "unit": "ft"},
                        {"label": "Length", "value": 20.0, "type": "dimension", "unit": "ft"},
                    ],
                }
            ]
        }
        create_property_sets(ifc, wall, properties, "feet")

        psets = ifc.by_type("IfcPropertySet")
        assert len(psets) == 1
        assert psets[0].Name == "Pset_Dimensions"

    def test_dimension_values_converted(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        properties = {
            "groups": [
                {
                    "label": "Dims",
                    "fields": [
                        {"label": "Height", "value": 10.0, "type": "dimension", "unit": "ft"},
                    ],
                }
            ]
        }
        create_property_sets(ifc, wall, properties, "feet")

        props = ifc.by_type("IfcPropertySingleValue")
        height_prop = [p for p in props if p.Name == "Height"][0]
        assert height_prop.NominalValue.wrappedValue == pytest.approx(10.0 * 0.3048)

    def test_text_value(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        properties = {
            "groups": [
                {
                    "label": "Identity",
                    "fields": [
                        {"label": "ID", "value": "wall_1", "type": "text"},
                    ],
                }
            ]
        }
        create_property_sets(ifc, wall, properties, "feet")

        props = ifc.by_type("IfcPropertySingleValue")
        id_prop = [p for p in props if p.Name == "ID"][0]
        assert id_prop.NominalValue.wrappedValue == "wall_1"

    def test_boolean_value(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        properties = {
            "groups": [
                {
                    "label": "Attrs",
                    "fields": [
                        {"label": "IsExterior", "value": True, "type": "boolean"},
                    ],
                }
            ]
        }
        create_property_sets(ifc, wall, properties, "feet")

        props = ifc.by_type("IfcPropertySingleValue")
        bool_prop = [p for p in props if p.Name == "IsExterior"][0]
        assert bool_prop.NominalValue.wrappedValue is True

    def test_none_properties_noop(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        create_property_sets(ifc, wall, None, "feet")
        assert len(ifc.by_type("IfcPropertySet")) == 0

    def test_empty_properties_noop(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        create_property_sets(ifc, wall, {}, "feet")
        assert len(ifc.by_type("IfcPropertySet")) == 0

    def test_rel_defines_by_properties(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        properties = {
            "groups": [
                {
                    "label": "Test",
                    "fields": [
                        {"label": "Val", "value": "x", "type": "text"},
                    ],
                }
            ]
        }
        create_property_sets(ifc, wall, properties, "feet")

        rels = ifc.by_type("IfcRelDefinesByProperties")
        assert len(rels) == 1
        assert wall in rels[0].RelatedObjects
