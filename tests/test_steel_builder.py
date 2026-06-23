"""Tests for the steel IFC builder and /convert-steel endpoints."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import ifcopenshell

from app.main import app
from app.services.ifc_builder import IFCBuilder
from app.models.schemas import SteelExportRequest


def make_transform(direction, up, pos):
    """Mirror steel_member._build_transform → 3x4 row-major [up|lat|dir|pos]."""
    d = np.array(direction, float); d /= np.linalg.norm(d)
    u = np.array(up, float); u /= np.linalg.norm(u)
    lat = np.cross(d, u); lat /= np.linalg.norm(lat)
    R = np.column_stack([u, lat, d, np.array(pos, float)])
    return R.flatten().tolist()


def steel_request_dict():
    """A small 2-storey steel model: columns, a beam, a joist, a footing."""
    return {
        "project": {"name": "Steel Test"},
        "source_units": "feet",
        "storeys": [
            {"id": "L1", "name": "Level 1", "elevation": 0.0},
            {"id": "L2", "name": "Level 2", "elevation": 12.0},
            {"id": "FND", "name": "Foundations", "elevation": -4.0},
        ],
        "members": [
            {
                "id": "col_1", "kind": "steel_w_column", "designation": "W12x53",
                "length_ft": 12.0, "floor_id": "L1",
                "transform": make_transform((0, 0, 1), (1, 0, 0), (0, 0, 0)),
                "properties": {"groups": [{"label": "Material", "fields": [
                    {"label": "Fy", "value": 50.0, "type": "number", "unit": "ksi"},
                ]}]},
            },
            {
                "id": "beam_1", "kind": "steel_w_beam", "designation": "W16x26",
                "length_ft": 30.0, "floor_id": "L2",
                "transform": make_transform((1, 0, 0), (0, 0, 1), (0, 0, 12)),
            },
            {
                "id": "joist_1", "kind": "steel_joist", "designation": "W12x14",
                "length_ft": 25.0, "floor_id": "L2",
                "transform": make_transform((0, 1, 0), (0, 0, 1), (0, 0, 12)),
            },
            {
                "id": "pad_1", "kind": "steel_foundation_pad", "floor_id": "FND",
                "footing": {"width_ft": 6.0, "depth_ft": 6.0, "thickness_ft": 2.0},
                "transform": make_transform((0, 0, 1), (1, 0, 0), (0, 0, -4)),
            },
        ],
    }


@pytest.fixture
def client():
    return TestClient(app)


class TestBuildSteel:
    def test_builds_expected_entities(self, tmp_path):
        req = SteelExportRequest(**steel_request_dict())
        data = IFCBuilder().build_steel(req)
        assert data.startswith(b"ISO-10303-21")

        p = tmp_path / "steel.ifc"
        p.write_bytes(data)
        ifc = ifcopenshell.open(str(p))

        assert len(ifc.by_type("IfcColumn")) == 1
        assert len(ifc.by_type("IfcBeam")) == 2          # beam + joist
        assert len(ifc.by_type("IfcFooting")) == 1
        assert len(ifc.by_type("IfcBuildingStorey")) == 3
        # Parametric geometry present.
        assert len(ifc.by_type("IfcIShapeProfileDef")) >= 3
        assert len(ifc.by_type("IfcExtrudedAreaSolid")) >= 4
        # Property set from the column's metadata.
        assert any(p.Name == "Pset_Material" for p in ifc.by_type("IfcPropertySet"))

    def test_members_assigned_to_storeys(self, tmp_path):
        req = SteelExportRequest(**steel_request_dict())
        data = IFCBuilder().build_steel(req)
        p = tmp_path / "steel.ifc"; p.write_bytes(data)
        ifc = ifcopenshell.open(str(p))

        # Map storey name -> set of contained element names.
        contained = {}
        for rel in ifc.by_type("IfcRelContainedInSpatialStructure"):
            contained[rel.RelatingStructure.Name] = {e.Name for e in rel.RelatedElements}
        assert "col_1" in contained.get("Level 1", set())
        assert {"beam_1", "joist_1"} <= contained.get("Level 2", set())
        assert "pad_1" in contained.get("Foundations", set())

    def test_no_storeys_falls_back(self):
        req = SteelExportRequest(**{**steel_request_dict(), "storeys": []})
        data = IFCBuilder().build_steel(req)
        assert data.startswith(b"ISO-10303-21")


class TestConvertSteelEndpoints:
    def test_sync_convert_steel(self, client):
        resp = client.post("/api/v1/convert-steel", json=steel_request_dict())
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert b"ISO-10303-21" in resp.content

    def test_async_convert_steel_job(self, client):
        resp = client.post("/api/v1/jobs/convert-steel", json=steel_request_dict())
        assert resp.status_code in (200, 201, 202)
        body = resp.json()
        assert "job_id" in body or "id" in body
