"""End-to-end validation of steel → IFC export from a fixture.

Posts a realistic steel model (column + beam + joist + footing) through the
/convert-steel endpoint, reloads the produced IFC, and validates structure and
geometry — including that every member solid actually tessellates (valid,
non-empty geometry) via ifcopenshell.geom.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ifcopenshell

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def steel_payload():
    return json.loads((FIXTURES_DIR / "simple_steel.json").read_text())


def _convert_and_open(client, payload, tmp_path):
    resp = client.post("/api/v1/convert-steel", json=payload)
    assert resp.status_code == 200
    assert b"ISO-10303-21" in resp.content
    p = tmp_path / "steel.ifc"
    p.write_bytes(resp.content)
    return ifcopenshell.open(str(p))


class TestSteelE2E:
    def test_structure(self, client, steel_payload, tmp_path):
        ifc = _convert_and_open(client, steel_payload, tmp_path)

        assert len(ifc.by_type("IfcColumn")) == 1
        assert len(ifc.by_type("IfcBeam")) == 2          # beam + joist
        assert len(ifc.by_type("IfcFooting")) == 1
        # Parametric profiles + solids present.
        assert len(ifc.by_type("IfcIShapeProfileDef")) == 3
        assert len(ifc.by_type("IfcExtrudedAreaSolid")) == 4

        # The footing has no supplied storey → a Foundations storey is synthesized.
        names = {s.Name for s in ifc.by_type("IfcBuildingStorey")}
        assert "Foundations" in names
        contained = {
            rel.RelatingStructure.Name: {e.Name for e in rel.RelatedElements}
            for rel in ifc.by_type("IfcRelContainedInSpatialStructure")
        }
        assert "pad_1" in contained.get("Foundations", set())
        assert "col_1" in contained.get("Level 1", set())
        assert {"beam_1", "joist_1"} <= contained.get("Level 2", set())

    def test_structural_unit_annotated(self, client, steel_payload, tmp_path):
        ifc = _convert_and_open(client, steel_payload, tmp_path)
        # Phase 0: the column's "kips" property carries a context-dependent unit.
        kips = [u for u in ifc.by_type("IfcContextDependentUnit") if u.Name == "kips"]
        assert len(kips) == 1
        steel_mats = [m for m in ifc.by_type("IfcMaterial") if m.Name == "Steel - A992"]
        assert steel_mats

    def test_all_member_solids_tessellate(self, client, steel_payload, tmp_path):
        """Every member must produce a valid, non-empty solid."""
        geom = pytest.importorskip("ifcopenshell.geom")
        ifc = _convert_and_open(client, steel_payload, tmp_path)

        settings = geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        members = (
            ifc.by_type("IfcColumn")
            + ifc.by_type("IfcBeam")
            + ifc.by_type("IfcFooting")
        )
        assert len(members) == 4
        for m in members:
            shape = geom.create_shape(settings, m)
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            assert len(verts) > 0, f"{m.Name}: no vertices"
            assert len(faces) > 0, f"{m.Name}: no faces"
            assert len(verts) % 3 == 0 and len(faces) % 3 == 0, m.Name
