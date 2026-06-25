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

    def test_inches_converted_to_metres(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Dims", "fields": [
            {"label": "Depth", "value": 24.0, "type": "dimension", "unit": "in"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Depth"][0]
        assert p.NominalValue.is_a() == "IfcLengthMeasure"
        assert p.NominalValue.wrappedValue == pytest.approx(24.0 * 0.0254)

    def test_area_converted(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Geo", "fields": [
            {"label": "Area", "value": 250.0, "type": "area", "unit": "sq ft"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Area"][0]
        assert p.NominalValue.is_a() == "IfcAreaMeasure"
        assert p.NominalValue.wrappedValue == pytest.approx(250.0 * 0.3048 ** 2)

    def test_volume_converted(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Geo", "fields": [
            {"label": "Vol", "value": 10.0, "type": "volume", "unit": "ft³"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Vol"][0]
        assert p.NominalValue.is_a() == "IfcVolumeMeasure"
        assert p.NominalValue.wrappedValue == pytest.approx(10.0 * 0.3048 ** 3)

    def test_angle_degrees_to_radians(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        import math
        props = {"groups": [{"label": "Geo", "fields": [
            {"label": "Slope", "value": 30.0, "type": "angle", "unit": "deg"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Slope"][0]
        assert p.NominalValue.is_a() == "IfcPlaneAngleMeasure"
        assert p.NominalValue.wrappedValue == pytest.approx(math.radians(30.0))

    def test_percentage(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Calc", "fields": [
            {"label": "PassRate", "value": 95.0, "type": "percentage", "unit": "%"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "PassRate"][0]
        assert p.NominalValue.is_a() == "IfcRatioMeasure"
        assert p.NominalValue.wrappedValue == pytest.approx(95.0)

    @pytest.mark.parametrize("unit", ["kips", "plf", "psf", "ksi", "kip-ft", "psi"])
    def test_structural_units_preserved_and_annotated(self, ifc_with_wall, unit):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Struct", "fields": [
            {"label": "Val", "value": 171.7, "type": "number", "unit": unit},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Val"][0]
        # Structural quantities are never rescaled.
        assert p.NominalValue.is_a() == "IfcReal"
        assert p.NominalValue.wrappedValue == pytest.approx(171.7)
        # ... and are annotated with a context-dependent unit carrying the symbol.
        assert p.Unit is not None
        assert p.Unit.is_a() == "IfcContextDependentUnit"
        assert p.Unit.Name == unit

    def test_unitless_number_is_real(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Calc", "fields": [
            {"label": "DCR", "value": 0.92, "type": "number"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "DCR"][0]
        assert p.NominalValue.is_a() == "IfcReal"
        assert p.NominalValue.wrappedValue == pytest.approx(0.92)
        assert p.Unit is None

    def test_list_joined_to_label(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Calc", "fields": [
            {"label": "Combo", "value": ["1.4D", "1.2D+1.6L"], "type": "list"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        p = [p for p in ifc.by_type("IfcPropertySingleValue") if p.Name == "Combo"][0]
        assert p.NominalValue.is_a() == "IfcLabel"
        assert p.NominalValue.wrappedValue == "1.4D, 1.2D+1.6L"

    def test_image_field_skipped(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Media", "fields": [
            {"label": "Thumb", "value": "data:image/png;base64,AAAA", "type": "image"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        names = [p.Name for p in ifc.by_type("IfcPropertySingleValue")]
        assert "Thumb" not in names
        # The group had no other emittable fields → no pset created.
        assert len(ifc.by_type("IfcPropertySet")) == 0

    def test_structural_unit_deduplicated(self, ifc_with_wall):
        ifc, wall = ifc_with_wall
        props = {"groups": [{"label": "Struct", "fields": [
            {"label": "Pu", "value": 100.0, "type": "number", "unit": "kips"},
            {"label": "Reaction", "value": 50.0, "type": "number", "unit": "kips"},
        ]}]}
        create_property_sets(ifc, wall, props, "feet")
        kips_units = [u for u in ifc.by_type("IfcContextDependentUnit") if u.Name == "kips"]
        assert len(kips_units) == 1  # reused, not duplicated

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
