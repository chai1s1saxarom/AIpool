import asyncio
import logging
from sqlalchemy.orm import Session

from app.clients import ServiceClients
from app.database import SessionLocal
from app.models import ChatMessage

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 1.0
MAX_POLL_ATTEMPTS = 90


def _map_job_status(raw: str) -> str:
    mapping = {
        "pending": "pending",
        "processing": "processing",
        "accepted": "pending",
        "done": "done",
        "failed": "failed",
        "cancelled": "failed",
    }
    return mapping.get(raw, "processing")


async def poll_request(request_id: str, clients: ServiceClients) -> None:
    """Опрашивает backend-задачу и обновляет сообщение в БД gateway."""
    for _ in range(MAX_POLL_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SEC)
        db: Session = SessionLocal()
        try:
            msg = db.query(ChatMessage).filter(ChatMessage.request_id == request_id).first()
            if not msg or not msg.backend_job_id:
                return
            if msg.status in ("done", "failed"):
                return

            if msg.processing_type == "llm":
                data = await clients.get_llm_job(msg.backend_job_id)
                status = _map_job_status(data.get("status", "pending"))
                msg.status = status
                if status == "done" and data.get("result"):
                    result = data["result"]
                    msg.result_content = result.get("response")
                    msg.total_cost_usd = result.get("total_cost_usd")
                    msg.processing_time_ms = data.get("processing_time_ms")
                    await clients.record_llm_cost(
                        str(msg.request_id),
                        msg.backend_job_id,
                        data.get("llm_model_id") or "openai_gpt-4o-mini",
                        result.get("input_tokens", 0),
                        result.get("output_tokens", 0),
                    )
                elif status == "failed":
                    msg.error = data.get("error_message") or "LLM job failed"

            elif msg.processing_type == "image":
                data = await clients.get_image_job(msg.backend_job_id)
                status = _map_job_status(data.get("status", "pending"))
                msg.status = status
                if status == "done":
                    image_id = data.get("result_image_id")
                    image_url = None
                    cost_usd = 0.04
                    if image_id:
                        try:
                            img = await clients.get_image(str(image_id))
                            image_url = img.get("image_url")
                        except Exception:  # noqa: BLE001
                            image_url = f"/images/{image_id}"
                    msg.result_content = image_url or "Image generated"
                    msg.processing_time_ms = data.get("processing_time_ms")
                    await clients.record_image_cost(
                        str(msg.request_id),
                        msg.backend_job_id,
                        cost_usd,
                    )
                    msg.total_cost_usd = cost_usd
                elif status == "failed":
                    msg.error = data.get("error_message") or "Image job failed"

            db.commit()
            if msg.status in ("done", "failed"):
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Poll error for %s: %s", request_id, exc)
            db.rollback()
        finally:
            db.close()


def schedule_poll(request_id: str, clients: ServiceClients) -> None:
    asyncio.create_task(poll_request(request_id, clients))
