"""Tests for parametric steel IFC geometry and element creation."""
import math

import numpy as np
import pytest

import ifcopenshell

from app.ifc.templates import create_ifc4_file
from app.ifc import steel_geometry
from app.ifc.profiles import get_profile
from app.services.element_mapper import create_ifc_steel_element

FT = 0.3048
IN = 0.0254


def make_transform(direction, up, pos):
    """Mirror steel_member._build_transform → 3x4 row-major [up|lat|dir|pos]."""
    d = np.array(direction, float); d /= np.linalg.norm(d)
    u = np.array(up, float); u /= np.linalg.norm(u)
    lat = np.cross(d, u); lat /= np.linalg.norm(lat)
    R = np.column_stack([u, lat, d, np.array(pos, float)])
    return R.flatten().tolist()


@pytest.fixture
def ifc_ctx():
    ifc, project, body = create_ifc4_file()
    return ifc, body


class TestProfileAndPlacement:
    def test_ishape_profile_dims_converted(self, ifc_ctx):
        ifc, _ = ifc_ctx
        dims = get_profile("W24x68")
        prof = steel_geometry.ishape_profile(ifc, dims, "W24x68")
        assert prof.is_a() == "IfcIShapeProfileDef"
        assert prof.OverallDepth == pytest.approx(dims["d"] * IN)
        assert prof.OverallWidth == pytest.approx(dims["bf"] * IN)
        assert prof.WebThickness == pytest.approx(dims["tw"] * IN)
        assert prof.FlangeThickness == pytest.approx(dims["tf"] * IN)

    def test_placement_from_transform(self, ifc_ctx):
        ifc, _ = ifc_ctx
        t = make_transform(direction=(1, 0, 0), up=(0, 0, 1), pos=(2, 3, 4))
        plc = steel_geometry.placement_from_transform(ifc, t, "feet")
        a2p = plc.RelativePlacement
        assert a2p.Location.Coordinates == pytest.approx((2 * FT, 3 * FT, 4 * FT))
        assert a2p.Axis.DirectionRatios == pytest.approx((1.0, 0.0, 0.0))         # direction
        assert a2p.RefDirection.DirectionRatios == pytest.approx((0.0, 0.0, 1.0))  # up

    def test_extrusion_rotates_profile_90deg(self, ifc_ctx):
        ifc, _ = ifc_ctx
        dims = get_profile("W16x26")
        solid = steel_geometry.ishape_extrusion(ifc, dims, 10.0, "feet")
        assert solid.Depth == pytest.approx(10.0 * FT)
        # Profile plane rotated so depth->local X, width->local Y.
        assert solid.Position.Axis.DirectionRatios == pytest.approx((0.0, 0.0, 1.0))
        assert solid.Position.RefDirection.DirectionRatios == pytest.approx((0.0, 1.0, 0.0))


class TestCreateSteelElement:
    def test_beam(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "beam_1", "kind": "steel_w_beam", "designation": "W16x26",
            "length_ft": 30.0, "transform": make_transform((1, 0, 0), (0, 0, 1), (0, 0, 12)),
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcBeam"
        assert el.PredefinedType == "BEAM"
        rep = el.Representation.Representations[0]
        assert rep.RepresentationType == "SweptSolid"
        assert rep.Items[0].is_a() == "IfcExtrudedAreaSolid"
        assert rep.Items[0].SweptArea.is_a() == "IfcIShapeProfileDef"
        # Material associated.
        mats = [r for r in ifc.by_type("IfcRelAssociatesMaterial") if el in r.RelatedObjects]
        assert mats and mats[0].RelatingMaterial.Name == "Steel - A992"

    def test_column(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "col_1", "kind": "steel_w_column", "designation": "W12x53",
            "length_ft": 12.0, "transform": make_transform((0, 0, 1), (1, 0, 0), (5, 5, 0)),
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcColumn"
        assert el.PredefinedType == "COLUMN"
        assert el.Representation.Representations[0].Items[0].is_a() == "IfcExtrudedAreaSolid"

    def test_joist_predefined(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "j1", "kind": "steel_joist", "designation": "W12x14",
            "length_ft": 25.0, "transform": make_transform((0, 1, 0), (0, 0, 1), (0, 0, 12)),
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcBeam"
        assert el.PredefinedType == "JOIST"

    def test_footing(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "pad_1", "kind": "steel_foundation_pad",
            "footing": {"width_ft": 6.0, "depth_ft": 6.0, "thickness_ft": 2.0},
            "transform": make_transform((0, 0, 1), (1, 0, 0), (5, 5, -4)),
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcFooting"
        assert el.PredefinedType == "PAD_FOOTING"
        solid = el.Representation.Representations[0].Items[0]
        assert solid.SweptArea.is_a() == "IfcRectangleProfileDef"
        assert solid.SweptArea.XDim == pytest.approx(6.0 * FT)
        assert solid.Depth == pytest.approx(2.0 * FT)
        mats = [r for r in ifc.by_type("IfcRelAssociatesMaterial") if el in r.RelatedObjects]
        assert mats and mats[0].RelatingMaterial.Name == "Concrete"

    def test_fallback_unknown_designation_no_mesh(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "x", "kind": "steel_w_beam", "designation": "W99x999",
            "length_ft": 10.0, "transform": make_transform((1, 0, 0), (0, 0, 1), (0, 0, 0)),
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcBuildingElementProxy"
        assert el.Representation is None  # geometry-less, no crash
        assert el.PredefinedType is None

    def test_fallback_uses_mesh_when_present(self, ifc_ctx):
        ifc, body = ifc_ctx
        member = {
            "id": "y", "kind": "steel_connection",
            "mesh": {"positions": [0, 0, 0, 1, 0, 0, 0, 1, 0], "indices": [0, 1, 2]},
        }
        el = create_ifc_steel_element(ifc, member, body)
        assert el.is_a() == "IfcBuildingElementProxy"
        assert el.Representation is not None

    def test_material_deduplicated(self, ifc_ctx):
        ifc, body = ifc_ctx
        for i in range(3):
            create_ifc_steel_element(ifc, {
                "id": f"b{i}", "kind": "steel_w_beam", "designation": "W16x26",
                "length_ft": 20.0, "transform": make_transform((1, 0, 0), (0, 0, 1), (0, 0, 0)),
            }, body)
        steels = [m for m in ifc.by_type("IfcMaterial") if m.Name == "Steel - A992"]
        assert len(steels) == 1


class TestOrientationEndToEnd:
    """Validate the full profile→placement→world chain via ifcopenshell.geom."""

    def test_horizontal_beam_world_aabb(self, ifc_ctx):
        geom = pytest.importorskip("ifcopenshell.geom")
        ifc, body = ifc_ctx
        dims = get_profile("W16x26")
        # Beam along +X, up=+Z, starting at origin, 10 ft long.
        member = {
            "id": "beam_x", "kind": "steel_w_beam", "designation": "W16x26",
            "length_ft": 10.0, "transform": make_transform((1, 0, 0), (0, 0, 1), (0, 0, 0)),
        }
        el = create_ifc_steel_element(ifc, member, body)

        settings = geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = geom.create_shape(settings, el)
        verts = np.array(shape.geometry.verts).reshape(-1, 3)
        ext = verts.max(axis=0) - verts.min(axis=0)

        # length along X, depth (d) along Z, flange width (bf) along Y.
        assert ext[0] == pytest.approx(10.0 * FT, abs=1e-3)
        assert ext[2] == pytest.approx(dims["d"] * IN, abs=2e-3)
        assert ext[1] == pytest.approx(dims["bf"] * IN, abs=2e-3)
