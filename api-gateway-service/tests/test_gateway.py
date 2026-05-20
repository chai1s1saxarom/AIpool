import uuid

import pytest
import respx
from httpx import Response


@pytest.mark.asyncio
async def test_create_chat_and_list(client):
    user_id = str(uuid.uuid4())
    r = await client.post("/v1/chats", json={"user_id": user_id, "name": "Test"})
    assert r.status_code == 201
    chat_id = r.json()["chat_id"]

    r = await client.get(f"/v1/chats?user_id={user_id}")
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert any(c["chat_id"] == chat_id for c in r.json()["items"])


@pytest.mark.asyncio
@respx.mock
async def test_send_llm_message_flow(client):
    user_id = str(uuid.uuid4())
    chat = await client.post("/v1/chats", json={"user_id": user_id})
    chat_id = chat.json()["chat_id"]
    request_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    respx.post("http://llm.test/v1/llm/jobs").mock(
        return_value=Response(202, json={"job_id": job_id, "user_request_id": request_id})
    )
    respx.get(f"http://llm.test/v1/llm/jobs/{job_id}").mock(
        return_value=Response(
            200,
            json={
                "job_id": job_id,
                "user_request_id": request_id,
                "status": "done",
                "result": {
                    "response": "Hello",
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_cost_usd": 0.001,
                },
                "processing_time_ms": 100,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
    )
    respx.post("http://cost.test/v2/costs").mock(return_value=Response(201, json={"id": str(uuid.uuid4())}))
    respx.get("http://cost.test/v1/costs").mock(return_value=Response(200, json={"items": [], "total": 0, "limit": 50, "offset": 0}))

    r = await client.post(
        "/v1/messages/send",
        json={
            "chat_id": chat_id,
            "user_id": user_id,
            "message": "Hi",
            "processing_type": "llm",
            "model_id": "openai_gpt-4o-mini",
        },
    )
    assert r.status_code == 202
    req_id = r.json()["request_id"]

    r = await client.get(f"/v1/messages/{req_id}/status")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_health_liveness(client):
    r = await client.get("/v1/health/liveness")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
