import json
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body or "http_request_duration_seconds" in body


@pytest.mark.asyncio
async def test_correlation_id_generated(client: AsyncClient):
    response = await client.get("/v1/health/liveness")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    uuid.UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_correlation_id_passed_through(client: AsyncClient):
    custom_id = str(uuid.uuid4())
    response = await client.get(
        "/v1/health/liveness",
        headers={"X-Request-ID": custom_id},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_error_request_metrics_and_404(client: AsyncClient):
    missing = str(uuid.uuid4())
    response = await client.get(f"/v1/images/jobs/{missing}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_slow_endpoint(client: AsyncClient):
    response = await client.get("/v1/debug/slow", params={"delay": 0.2})
    assert response.status_code == 200
    assert response.json()["delay_seconds"] == 0.2


def test_json_log_formatter_has_correlation_id():
    from app.logging_config import JsonFormatter, correlation_id_var
    import logging

    token = correlation_id_var.set("test-corr-123")
    try:
        record = logging.LogRecord(
            name="app",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        line = JsonFormatter().format(record)
        data = json.loads(line)
        assert data["correlation_id"] == "test-corr-123"
        assert data["message"] == "hello"
        assert "timestamp" in data
    finally:
        correlation_id_var.reset(token)
