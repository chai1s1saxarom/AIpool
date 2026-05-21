"""
API Gateway / Router — связывает LLM, Image и Cost Accounting сервисы.
Реализует OpenAPI api-router-service + веб-интерфейс.
"""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models, schemas
from app.clients import (
    COST_SERVICE_URL,
    IMAGE_SERVICE_URL,
    LLM_SERVICE_URL,
    ServiceClients,
)
from app.database import Base, engine, get_db
from app.orchestrator import schedule_poll

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(30.0, connect=10.0)
    app.state.http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    app.state.clients = ServiceClients(app.state.http_client)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="API Gateway Service",
    description="Единая точка входа для UI и оркестрации микросервисов AI Pool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


def _clients(request) -> ServiceClients:
    return request.app.state.clients


@app.get("/", include_in_schema=False)
async def ui_index():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "api-gateway", "ui": "/assets/index.html"}


@app.get("/v1/services/status", response_model=schemas.ServicesStatusResponse, tags=["info"])
async def services_status(request: Request):
    c: ServiceClients = _clients(request)
    return schemas.ServicesStatusResponse(
        gateway="ok",
        llm="ok" if await c.health(LLM_SERVICE_URL) else "error",
        image="ok" if await c.health(IMAGE_SERVICE_URL) else "error",
        cost="ok" if await c.health(COST_SERVICE_URL) else "error",
    )


@app.get("/v1/chats", response_model=schemas.ChatListResponse, tags=["chats"])
def list_chats(
    user_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.Chat).filter(models.Chat.user_id == user_id, models.Chat.status == "active")
    total = q.count()
    items = q.order_by(models.Chat.created_at.desc()).offset(offset).limit(limit).all()
    return schemas.ChatListResponse(
        items=[schemas.ChatResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post("/v1/chats", response_model=schemas.ChatResponse, status_code=201, tags=["chats"])
def create_chat(body: schemas.CreateChatRequest, db: Session = Depends(get_db)):
    chat = models.Chat(user_id=body.user_id, name=body.name, status="active")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return schemas.ChatResponse.model_validate(chat)


@app.get("/v1/chats/{chat_id}", response_model=schemas.ChatResponse, tags=["chats"])
def get_chat(chat_id: UUID, db: Session = Depends(get_db)):
    chat = db.get(models.Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Чат не найден"})
    return schemas.ChatResponse.model_validate(chat)


@app.delete("/v1/chats/{chat_id}", status_code=204, tags=["chats"])
def delete_chat(chat_id: UUID, db: Session = Depends(get_db)):
    chat = db.get(models.Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Чат не найден"})
    chat.status = "closed"
    db.commit()
    return None


@app.get("/v1/chats/{chat_id}/history", response_model=schemas.ChatHistoryResponse, tags=["chats"])
def get_chat_history(
    chat_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    chat = db.get(models.Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Чат не найден"})
    q = db.query(models.ChatMessage).filter(models.ChatMessage.chat_id == chat_id)
    total = q.count()
    messages = q.order_by(models.ChatMessage.created_at.asc()).offset(offset).limit(limit).all()
    return schemas.ChatHistoryResponse(
        chat_id=chat_id,
        messages=[schemas.ChatMessageSchema.model_validate(m) for m in messages],
        total=total,
    )


@app.post("/v1/messages/send", response_model=schemas.MessageAcceptedResponse, status_code=202, tags=["messages"])
async def send_message(body: schemas.SendMessageRequest, request: Request, db: Session = Depends(get_db)):
    chat = db.get(models.Chat, body.chat_id)
    if not chat or chat.status != "active":
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Чат не найден"})
    if chat.user_id != body.user_id:
        raise HTTPException(status_code=400, detail={"error": "USER_MISMATCH", "message": "user_id не совпадает с чатом"})

    request_id = uuid.uuid4()
    clients: ServiceClients = _clients(request)

    user_msg = models.ChatMessage(
        chat_id=body.chat_id,
        request_id=request_id,
        role="user",
        content=body.message,
        processing_type=body.processing_type,
        status="done",
    )
    db.add(user_msg)

    assistant_msg = models.ChatMessage(
        chat_id=body.chat_id,
        request_id=uuid.uuid4(),
        role="assistant",
        content="Обработка…",
        processing_type=body.processing_type,
        status="pending",
    )
    db.flush()

    try:
        if body.processing_type == "llm":
            created = await clients.create_llm_job(
                str(request_id),
                body.model_id or "openai_gpt-4o-mini",
                body.message,
                body.temperature,
                body.max_tokens,
            )
            assistant_msg.backend_job_id = created["job_id"]
            assistant_msg.request_id = request_id
        else:
            created = await clients.create_image_job(
                str(request_id),
                body.message,
                body.provider_id or "dalle-3",
            )
            assistant_msg.backend_job_id = str(created["job_id"])
            assistant_msg.request_id = request_id
    except httpx.HTTPStatusError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={"error": "UPSTREAM_ERROR", "message": str(e.response.text)},
        ) from e
    except httpx.HTTPError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail={"error": "UPSTREAM_UNAVAILABLE", "message": str(e)}) from e

    db.add(assistant_msg)
    db.commit()
    schedule_poll(str(request_id), clients)

    return schemas.MessageAcceptedResponse(request_id=request_id)


@app.get("/v1/messages/{request_id}/status", response_model=schemas.MessageStatusResponse, tags=["messages"])
async def get_message_status(request_id: UUID, request: Request, db: Session = Depends(get_db)):
    msg = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.request_id == request_id,
            models.ChatMessage.role == "assistant",
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Запрос не найден"})

    clients: ServiceClients = _clients(request)
    result = None
    status = msg.status

    if msg.backend_job_id and msg.status not in ("done", "failed"):
        try:
            if msg.processing_type == "llm":
                data = await clients.get_llm_job(msg.backend_job_id)
                status = data.get("status", msg.status)
                if status == "done" and data.get("result"):
                    r = data["result"]
                    result = schemas.MessageResult(
                        content=r.get("response"),
                        input_tokens=r.get("input_tokens"),
                        output_tokens=r.get("output_tokens"),
                        total_cost_usd=r.get("total_cost_usd"),
                        model_id=data.get("llm_model_id"),
                    )
            elif msg.processing_type == "image":
                data = await clients.get_image_job(msg.backend_job_id)
                status = data.get("status", msg.status)
                if status == "done" and data.get("result_image_id"):
                    try:
                        img = await clients.get_image(str(data["result_image_id"]))
                        result = schemas.MessageResult(
                            content=img.get("prompt"),
                            image_url=img.get("image_url"),
                            total_cost_usd=0.04,
                        )
                    except httpx.HTTPError:
                        result = schemas.MessageResult(content="Image ready", total_cost_usd=0.04)
        except httpx.HTTPError:
            pass

    costs = await clients.get_costs_by_request(str(request_id))
    costs_summary = None
    if costs:
        costs_summary = {
            "total_usd": round(sum(c.get("usd_amount", 0) or 0 for c in costs), 4),
            "records": len(costs),
        }

    if msg.result_content and not result:
        result = schemas.MessageResult(content=msg.result_content, total_cost_usd=msg.total_cost_usd)

    return schemas.MessageStatusResponse(
        request_id=request_id,
        status=status if status in ("pending", "processing", "done", "failed") else "processing",
        result=result,
        error=msg.error,
        processing_time_ms=msg.processing_time_ms,
        costs_summary=costs_summary,
    )


@app.get("/v1/health/liveness", response_model=schemas.HealthResponse, tags=["health"])
def health_liveness():
    return schemas.HealthResponse(status="healthy")


@app.get("/v1/health/readiness", response_model=schemas.HealthResponse, tags=["health"])
async def health_readiness(request: Request, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = "ok"
    except Exception:
        db_ok = "error"

    c: ServiceClients = _clients(request)
    llm_ok = "ok" if await c.health(LLM_SERVICE_URL) else "error"
    image_ok = "ok" if await c.health(IMAGE_SERVICE_URL) else "error"
    cost_ok = "ok" if await c.health(COST_SERVICE_URL) else "error"

    details = {
        "database": db_ok,
        "llm_service": llm_ok,
        "image_service": image_ok,
        "cost_service": cost_ok,
        "rabbitmq": "n/a",
        "redis": "n/a",
    }
    healthy = all(v == "ok" for k, v in details.items() if k in ("database", "llm_service", "image_service", "cost_service"))
    status = "healthy" if healthy else "unhealthy"
    if not healthy:
        raise HTTPException(status_code=503, detail=schemas.HealthResponse(status=status, details=details).model_dump())
    return schemas.HealthResponse(status=status, details=details)
