"""
LLM Processing Service
======================
Покрывает практические работы:
  №3 — Docker-контейнеризация
  №4 — Микросервисная архитектура, Docker Compose
  №5 — PostgreSQL + SQLAlchemy + CRUD
  №6 — async/await, asyncio.gather, BackgroundTasks
  №7 — RabbitMQ producer + consumer
"""
import uuid
import time
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import models, schemas
from app.database import engine, get_db
from app.models_registry import MODELS
from app.rabbit import publish_job, check_rabbitmq

# Создаём таблицы при старте (Практика №5)
models.LLMJob.__table__.create(bind=engine, checkfirst=True)

app = FastAPI(
    title="LLM Processing Service",
    description=(
        "Сервис асинхронной обработки запросов к LLM-провайдерам.\n\n"
        "**Практика №5** — PostgreSQL + SQLAlchemy + CRUD\n\n"
        "**Практика №6** — async/await, BackgroundTasks\n\n"
        "**Практика №7** — RabbitMQ: producer при создании задачи, "
        "consumer обрабатывает задачи из очереди"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Вспомогательные функции ───────────────────────────────────

def _job_to_response(job: models.LLMJob) -> schemas.LLMJobResponse:
    """Конвертация ORM-объекта в Pydantic-схему."""
    result = None
    if job.status == "done" and job.result_response:
        result = schemas.LLMResult(
            response=job.result_response,
            input_tokens=job.result_input_tokens or 0,
            output_tokens=job.result_output_tokens or 0,
            total_cost_usd=job.result_total_cost_usd or 0.0,
        )
    return schemas.LLMJobResponse(
        job_id=job.job_id,
        user_request_id=job.user_request_id,
        llm_model_id=job.llm_model_id,
        consumer_service_id=job.consumer_service_id,
        status=schemas.JobStatus(job.status),
        result=result,
        error_message=job.error_message,
        processing_time_ms=job.processing_time_ms,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _write_log(message: str) -> None:
    """
    Фоновая задача — запись в лог-файл (Практика №6 — BackgroundTasks).
    Выполняется ПОСЛЕ того, как ответ ушёл клиенту.
    """
    with open("/app/service.log", "a") as f:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts} — {message}\n")


# ── Корень ────────────────────────────────────────────────────

@app.get("/", tags=["info"])
def root():
    return {
        "service": "llm-processing-service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


# ── Health (Практика №4) ──────────────────────────────────────

@app.get(
    "/v1/health/liveness",
    response_model=schemas.HealthResponse,
    tags=["health"],
    summary="Проверка живости",
)
def health_liveness():
    """Сервис запущен и отвечает на запросы."""
    return schemas.HealthResponse(status="healthy")


@app.get(
    "/v1/health/readiness",
    response_model=schemas.HealthResponse,
    tags=["health"],
    summary="Проверка готовности",
)
def health_readiness(db: Session = Depends(get_db)):
    """
    Проверяет PostgreSQL и RabbitMQ.
    Возвращает 503, если хотя бы один недоступен.
    """
    db_ok = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = "error"

    rmq_ok = "ok" if check_rabbitmq() else "error"

    status = "healthy" if db_ok == "ok" and rmq_ok == "ok" else "unhealthy"
    response = schemas.HealthResponse(
        status=status,
        details=schemas.HealthDetails(database=db_ok, rabbitmq=rmq_ok),
    )
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail=response.dict())
    return response


# ── Модели ────────────────────────────────────────────────────

@app.get(
    "/v1/models",
    response_model=schemas.ModelListResponse,
    tags=["models"],
    summary="Список доступных LLM-моделей",
)
def list_models():
    """Все поддерживаемые модели с ценами и лимитами токенов."""
    return schemas.ModelListResponse(models=list(MODELS.values()))


@app.get(
    "/v1/models/{model_id}",
    response_model=schemas.ModelInfo,
    tags=["models"],
    summary="Информация о конкретной модели",
)
def get_model(model_id: str):
    model = MODELS.get(model_id)
    if not model:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": f"Модель '{model_id}' не найдена"},
        )
    return model


# ── LLM Jobs — CRUD (Практика №5) ────────────────────────────

@app.get(
    "/v1/llm/jobs",
    response_model=schemas.LLMJobListResponse,
    tags=["jobs"],
    summary="Список задач",
)
def list_jobs(
    user_request_id: Optional[str] = Query(None, description="Фильтр по ID запроса"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Список задач с фильтрацией и пагинацией."""
    query = db.query(models.LLMJob)
    if user_request_id:
        query = query.filter(models.LLMJob.user_request_id == user_request_id)
    if status:
        query = query.filter(models.LLMJob.status == status)

    total = query.count()
    jobs = query.order_by(models.LLMJob.created_at.desc()).offset(offset).limit(limit).all()

    return schemas.LLMJobListResponse(
        items=[_job_to_response(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/v1/llm/jobs",
    response_model=schemas.LLMJobCreatedResponse,
    status_code=202,
    tags=["jobs"],
    summary="Создать LLM-задачу",
)
async def create_job(
    request: schemas.CreateLLMJobRequest,
    background_tasks: BackgroundTasks,       # Практика №6
    db: Session = Depends(get_db),
):
    """
    Создаёт задачу и немедленно возвращает job_id (асинхронная обработка).

    После ответа клиенту в фоне (BackgroundTasks — Практика №6):
    - публикует задачу в RabbitMQ (Практика №7)
    - пишет запись в лог-файл
    """
    if request.llm_model_id not in MODELS:
        raise HTTPException(
            status_code=422,
            detail={"error": "UNKNOWN_MODEL", "message": f"Модель '{request.llm_model_id}' не поддерживается"},
        )

    job_id = str(uuid.uuid4())
    messages_raw = [m.dict() for m in request.messages]

    # Сохраняем в PostgreSQL (Практика №5)
    db_job = models.LLMJob(
        job_id=job_id,
        user_request_id=request.user_request_id,
        llm_model_id=request.llm_model_id,
        consumer_service_id=request.consumer_service_id,
        status="pending",
        messages=messages_raw,
        webhook_url=request.webhook_url,
        timeout=request.timeout,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        structured_output=request.structured_output,
    )
    db.add(db_job)
    db.commit()

    # Фоновые задачи (Практика №6 — BackgroundTasks)
    background_tasks.add_task(
        publish_job,
        job_id,
        {
            "job_id": job_id,
            "llm_model_id": request.llm_model_id,
            "messages": messages_raw,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        },
    )
    background_tasks.add_task(
        _write_log,
        f"Job created: job_id={job_id}, model={request.llm_model_id}, "
        f"consumer={request.consumer_service_id}",
    )

    return schemas.LLMJobCreatedResponse(
        job_id=job_id,
        user_request_id=request.user_request_id,
    )


@app.get(
    "/v1/llm/jobs/{job_id}",
    response_model=schemas.LLMJobResponse,
    tags=["jobs"],
    summary="Статус и результат задачи",
)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Получить задачу по UUID. Polling этого эндпоинта — стандартный способ дождаться результата."""
    job = db.get(models.LLMJob, job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": f"Задача '{job_id}' не найдена"},
        )
    return _job_to_response(job)


@app.delete(
    "/v1/llm/jobs/{job_id}",
    response_model=schemas.LLMJobResponse,
    tags=["jobs"],
    summary="Отменить задачу",
)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """Отменяет задачу если она ещё не завершена. Возвращает 409 если уже done/failed."""
    job = db.get(models.LLMJob, job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": f"Задача '{job_id}' не найдена"},
        )
    if job.status in ("done", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail={"error": "ALREADY_FINISHED", "message": f"Задача уже в статусе '{job.status}'"},
        )
    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return _job_to_response(job)


# ── Трейс (Практика №6 — async def) ──────────────────────────

@app.get(
    "/v1/llm/trace/{user_request_id}",
    response_model=schemas.LLMTraceResponse,
    tags=["jobs"],
    summary="Трейс всех задач одного запроса",
)
async def get_trace(user_request_id: str, db: Session = Depends(get_db)):
    """
    Все LLM-задачи для одного user_request_id с агрегацией стоимости.
    async def — сервис не блокирует event loop пока обрабатывает запрос.
    """
    jobs = (
        db.query(models.LLMJob)
        .filter(models.LLMJob.user_request_id == user_request_id)
        .order_by(models.LLMJob.created_at)
        .all()
    )
    if not jobs:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": f"Трейс '{user_request_id}' не найден"},
        )

    total_cost = sum(j.result_total_cost_usd or 0 for j in jobs)
    total_input = sum(j.result_input_tokens or 0 for j in jobs)
    total_output = sum(j.result_output_tokens or 0 for j in jobs)

    return schemas.LLMTraceResponse(
        user_request_id=user_request_id,
        jobs=[_job_to_response(j) for j in jobs],
        total_cost_usd=round(total_cost, 6),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )
