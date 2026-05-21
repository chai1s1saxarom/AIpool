import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import correlation_id_var

logger = logging.getLogger("app.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Создаёт или принимает X-Request-ID и добавляет correlation_id в логи и ответ."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Request-ID") or str(uuid4())
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = correlation_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            if request.url.path != "/metrics":
                log_record = logger.makeRecord(
                    logger.name,
                    logging.INFO,
                    __file__,
                    0,
                    f"{request.method} {request.url.path} {status_code}",
                    (),
                    None,
                )
                log_record.method = request.method
                log_record.path = request.url.path
                log_record.status_code = status_code
                log_record.duration_ms = duration_ms
                logger.handle(log_record)
            correlation_id_var.reset(token)
