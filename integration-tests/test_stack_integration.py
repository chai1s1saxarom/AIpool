"""
Интеграционные тесты полного стека (gateway + llm + image + cost).
Запуск: RUN_INTEGRATION=1 pytest integration-tests/ -m integration
После: docker compose up -d --build
"""
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration


def test_services_status(gateway: httpx.Client):
    r = gateway.get("/v1/services/status")
    assert r.status_code == 200
    data = r.json()
    assert data["gateway"] == "ok"
    assert data["llm"] == "ok"
    assert data["image"] == "ok"
    assert data["cost"] == "ok"


def test_llm_end_to_end_via_gateway(gateway: httpx.Client):
    user_id = str(uuid.uuid4())
    chat = gateway.post("/v1/chats", json={"user_id": user_id, "name": "E2E LLM"})
    assert chat.status_code == 201
    chat_id = chat.json()["chat_id"]

    sent = gateway.post(
        "/v1/messages/send",
        json={
            "chat_id": chat_id,
            "user_id": user_id,
            "message": "Интеграционный тест LLM",
            "processing_type": "llm",
            "model_id": "openai_gpt-4o-mini",
        },
    )
    assert sent.status_code == 202
    request_id = sent.json()["request_id"]

    deadline = time.time() + 60
    status = "pending"
    while time.time() < deadline:
        st = gateway.get(f"/v1/messages/{request_id}/status")
        assert st.status_code == 200
        status = st.json()["status"]
        if status == "done":
            assert st.json().get("result") is not None
            break
        if status == "failed":
            pytest.fail(st.json().get("error"))
        time.sleep(1.5)
    else:
        pytest.fail(f"LLM job did not complete, last status: {status}")


def test_image_end_to_end_via_gateway(gateway: httpx.Client):
    user_id = str(uuid.uuid4())
    chat = gateway.post("/v1/chats", json={"user_id": user_id, "name": "E2E Image"})
    assert chat.status_code == 201
    chat_id = chat.json()["chat_id"]

    sent = gateway.post(
        "/v1/messages/send",
        json={
            "chat_id": chat_id,
            "user_id": user_id,
            "message": "sunset over mountains",
            "processing_type": "image",
            "provider_id": "dalle-3",
        },
    )
    assert sent.status_code == 202
    request_id = sent.json()["request_id"]

    deadline = time.time() + 30
    status = "pending"
    while time.time() < deadline:
        st = gateway.get(f"/v1/messages/{request_id}/status")
        status = st.json()["status"]
        if status == "done":
            break
        if status == "failed":
            pytest.fail(st.json().get("error"))
        time.sleep(1.0)
    else:
        pytest.fail(f"Image job timeout, status={status}")
