import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient


def _job_payload(user_request_id: str | None = None) -> dict:
    return {
        "prompt": "test prompt",
        "user_request_id": user_request_id or str(uuid.uuid4()),
        "consumer_service_id": "pytest",
        "provider_id": "dalle-3",
        "operation": "generate",
    }


@pytest.mark.asyncio
async def test_job_crud_flow(client: AsyncClient):
    rid = str(uuid.uuid4())
    r = await client.post("/v1/images/jobs", json=_job_payload(rid))
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    r = await client.get("/v1/images/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(item["job_id"] == job_id for item in data["items"])

    r = await client.get(f"/v1/images/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["prompt"] == "test prompt"

    r = await client.put(f"/v1/images/jobs/{job_id}", json={"prompt": "updated"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "updated"

    r = await client.delete(f"/v1/images/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_job_not_found(client: AsyncClient):
    missing = str(uuid.uuid4())
    r = await client.get(f"/v1/images/jobs/{missing}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_unknown_provider_422(client: AsyncClient):
    body = _job_payload()
    body["provider_id"] = "unknown"
    r = await client.post("/v1/images/jobs", json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_image_crud(client: AsyncClient):
    r = await client.post(
        "/v1/images",
        json={"image_url": "https://example.com/a.png", "prompt": "p"},
    )
    assert r.status_code == 201
    image_id = r.json()["image_id"]

    r = await client.get("/v1/images")
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    r = await client.get(f"/v1/images/{image_id}")
    assert r.status_code == 200

    r = await client.put(f"/v1/images/{image_id}", json={"prompt": "new"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "new"

    r = await client.delete(f"/v1/images/{image_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_post_job_writes_log_row(client: AsyncClient):
    r = await client.post("/v1/images/jobs", json=_job_payload())
    assert r.status_code == 202
    deadline = time.time() + 2.0
    ok = False
    while time.time() < deadline:
        lr = await client.get("/v1/logs")
        if lr.status_code == 200 and lr.json():
            ok = any(entry["action"] == "create_job" for entry in lr.json())
            if ok:
                break
        await asyncio.sleep(0.05)
    assert ok, "ожидалась запись лога create_job от BackgroundTasks"


@pytest.mark.asyncio
async def test_external_post(client: AsyncClient):
    r = await client.get("/v1/external/posts/1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert "title" in body


@pytest.mark.asyncio
async def test_external_aggregate(client: AsyncClient):
    r = await client.get("/v1/external/aggregate")
    assert r.status_code == 200
    data = r.json()
    assert data.get("posts_sample") or data.get("users_sample") or data.get("todos_sample")
    assert not data.get("errors")
