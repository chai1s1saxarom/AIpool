import os

from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app) -> Instrumentator | None:
    if os.getenv("ENABLE_METRICS", "true").lower() in ("0", "false", "no"):
        return None
    """Эндпоинт /metrics и стандартные метрики Prometheus для Grafana."""
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=False,
        should_respect_env_var=False,
        excluded_handlers=["/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)
    return instrumentator
