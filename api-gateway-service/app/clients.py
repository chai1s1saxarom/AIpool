import os
from typing import Any, Optional

import httpx

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8001").rstrip("/")
IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL", "http://localhost:8002").rstrip("/")
COST_SERVICE_URL = os.getenv("COST_SERVICE_URL", "http://localhost:8003").rstrip("/")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))


class ServiceClients:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def health(self, base_url: str) -> bool:
        try:
            r = await self.client.get(f"{base_url}/v1/health/liveness", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def create_llm_job(
        self,
        user_request_id: str,
        model_id: str,
        message: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "messages": [{"role": "user", "content": message}],
            "user_request_id": user_request_id,
            "llm_model_id": model_id,
            "consumer_service_id": "api-gateway",
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = await self.client.post(f"{LLM_SERVICE_URL}/v1/llm/jobs", json=payload)
        r.raise_for_status()
        return r.json()

    async def get_llm_job(self, job_id: str) -> dict[str, Any]:
        r = await self.client.get(f"{LLM_SERVICE_URL}/v1/llm/jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    async def create_image_job(self, user_request_id: str, prompt: str, provider_id: str) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "user_request_id": user_request_id,
            "consumer_service_id": "api-gateway",
            "provider_id": provider_id,
            "operation": "generate",
            "size": "1024x1024",
        }
        r = await self.client.post(f"{IMAGE_SERVICE_URL}/v1/images/jobs", json=payload)
        r.raise_for_status()
        return r.json()

    async def get_image_job(self, job_id: str) -> dict[str, Any]:
        r = await self.client.get(f"{IMAGE_SERVICE_URL}/v1/images/jobs/{job_id}")
        r.raise_for_status()
        return r.json()

    async def get_image(self, image_id: str) -> dict[str, Any]:
        r = await self.client.get(f"{IMAGE_SERVICE_URL}/v1/images/{image_id}")
        r.raise_for_status()
        return r.json()

    async def record_llm_cost(
        self,
        user_request_id: str,
        job_id: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> Optional[dict[str, Any]]:
        payload = {
            "service_name": "llm-processing-service",
            "user_request_id": user_request_id,
            "job_id": job_id,
            "model_id": model_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        try:
            r = await self.client.post(f"{COST_SERVICE_URL}/v2/costs", json=payload)
            if r.status_code in (200, 201):
                return r.json()
        except httpx.HTTPError:
            return None
        return None

    async def record_image_cost(
        self,
        user_request_id: str,
        job_id: str,
        amount_usd: float,
    ) -> Optional[dict[str, Any]]:
        payload = {
            "service_name": "image-processing-service",
            "user_request_id": user_request_id,
            "job_id": job_id,
            "currency": "USD",
            "amount": max(amount_usd, 0.01),
        }
        try:
            r = await self.client.post(f"{COST_SERVICE_URL}/v1/costs", json=payload)
            if r.status_code in (200, 201):
                return r.json()
        except httpx.HTTPError:
            return None
        return None

    async def get_costs_by_request(self, user_request_id: str) -> list[dict[str, Any]]:
        try:
            r = await self.client.get(
                f"{COST_SERVICE_URL}/v1/costs",
                params={"user_request_id": user_request_id, "limit": 50},
            )
            if r.status_code == 200:
                return r.json().get("items", [])
        except httpx.HTTPError:
            pass
        return []
