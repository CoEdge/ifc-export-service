"""Tests for the async jobs API endpoints."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.main import app
from app.services.job_manager import get_job_manager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def async_client():
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_job_manager():
    """Reset the job manager state between tests."""
    jm = get_job_manager()
    jm._jobs.clear()
    jm._tasks.clear()
    from app.api.jobs_router import _ifc_file_cache
    _ifc_file_cache.clear()
    yield


async def _poll_until_done(
    client: httpx.AsyncClient,
    job_id: str,
    timeout: float = 30.0,
    include_result: bool = False,
):
    """Poll a job until completed or timeout."""
    import time
    start = time.monotonic()
    params = {"include_result": "true"} if include_result else {}
    while time.monotonic() - start < timeout:
        resp = await client.get(f"/api/v1/jobs/{job_id}", params=params)
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


class TestJobConvertEndpoint:
    """Test POST /api/v1/jobs/convert (job creation + polling + download)."""

    @pytest.mark.asyncio
    async def test_create_job_returns_immediately(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] in ("pending", "running")
        assert data["poll_url"].startswith("/api/v1/jobs/")

    @pytest.mark.asyncio
    async def test_poll_until_completed(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        job_id = resp.json()["job_id"]

        data = await _poll_until_done(async_client, job_id, include_result=True)

        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert data["result"] is not None
        assert "file_size" in data["result"]
        assert "download_url" in data["result"]

    @pytest.mark.asyncio
    async def test_download_ifc_file(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        job_id = resp.json()["job_id"]

        await _poll_until_done(async_client, job_id)

        download_resp = await async_client.get(f"/api/v1/jobs/{job_id}/download")
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"] == "application/octet-stream"
        assert b"ISO-10303-21" in download_resp.content
        assert "model.ifc" in download_resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_result_endpoint(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        job_id = resp.json()["job_id"]

        await _poll_until_done(async_client, job_id)

        result_resp = await async_client.get(f"/api/v1/jobs/{job_id}/result")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["element_count"] == 1
        assert data["file_size"] > 0

    @pytest.mark.asyncio
    async def test_house_model_job(self, async_client):
        payload = json.loads((FIXTURES_DIR / "house_model.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        job_id = resp.json()["job_id"]

        data = await _poll_until_done(async_client, job_id, include_result=True)

        assert data["status"] == "completed"
        assert data["result"]["element_count"] == 6


class TestJobManagementEndpoints:
    """Test job CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, async_client):
        resp = await async_client.get("/api/v1/jobs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, async_client):
        resp = await async_client.get("/api/v1/jobs/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["jobs"] == []

    @pytest.mark.asyncio
    async def test_list_jobs_after_creation(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        await async_client.post("/api/v1/jobs/convert", json=payload)

        resp = await async_client.get("/api/v1/jobs/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self, async_client):
        resp = await async_client.delete("/api/v1/jobs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_job_info(self, async_client):
        payload = json.loads((FIXTURES_DIR / "simple_wall.json").read_text())
        resp = await async_client.post("/api/v1/jobs/convert", json=payload)
        job_id = resp.json()["job_id"]

        status_resp = await async_client.get(f"/api/v1/jobs/{job_id}")
        data = status_resp.json()
        assert data["job_id"] == job_id
        assert data["type"] == "ifc-convert"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_download_nonexistent_job(self, async_client):
        resp = await async_client.get("/api/v1/jobs/nonexistent-id/download")
        assert resp.status_code == 404
