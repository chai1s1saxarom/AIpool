import os
import time

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
LLM_URL = os.getenv("LLM_URL", "http://llm-service:8000")
IMAGE_URL = os.getenv("IMAGE_URL", "http://image-service:8000")
COST_URL = os.getenv("COST_URL", "http://cost-service:8000")
INTEGRATION_ENABLED = os.getenv("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: cross-service tests (need docker compose)")


@pytest.fixture(scope="session")
def gateway_ready():
    if not INTEGRATION_ENABLED:
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{GATEWAY_URL}/v1/health/readiness")
                if r.status_code == 200:
                    return GATEWAY_URL
        except httpx.HTTPError:
            pass
        time.sleep(2)
    pytest.fail("Gateway not ready within timeout")


@pytest.fixture
def gateway(gateway_ready):
    with httpx.Client(base_url=gateway_ready, timeout=60.0) as client:
        yield client
