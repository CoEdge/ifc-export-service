import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_root_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_v1_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


class TestConvertEndpoint:
    def test_simple_wall(self, client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = client.post("/api/v1/convert", json=payload)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert b"ISO-10303-21" in resp.content  # STEP file signature

    def test_house_model(self, client):
        payload = json.loads((FIXTURES_DIR / "house_model.json").read_text())
        resp = client.post("/api/v1/convert", json=payload)
        assert resp.status_code == 200
        assert b"ISO-10303-21" in resp.content

    def test_invalid_payload(self, client):
        resp = client.post("/api/v1/convert", json={"elements": "not_a_list"})
        assert resp.status_code == 422

    def test_empty_elements(self, client):
        payload = {"elements": []}
        resp = client.post("/api/v1/convert", json=payload)
        # Should succeed with an IFC file containing just the spatial structure
        assert resp.status_code == 200
        assert b"ISO-10303-21" in resp.content

    def test_content_disposition(self, client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = client.post("/api/v1/convert", json=payload)
        assert "model.ifc" in resp.headers.get("content-disposition", "")
