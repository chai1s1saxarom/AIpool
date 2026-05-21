from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateChatRequest(BaseModel):
    user_id: UUID
    name: Optional[str] = Field(None, max_length=255)
    metadata: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    chat_id: UUID
    user_id: UUID
    name: Optional[str] = None
    status: Literal["active", "closed"]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatListResponse(BaseModel):
    items: list[ChatResponse]
    total: int
    limit: int
    offset: int


class ChatMessageSchema(BaseModel):
    message_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    processing_type: Optional[Literal["llm", "image"]] = None
    status: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    chat_id: UUID
    messages: list[ChatMessageSchema]
    total: int


class SendMessageRequest(BaseModel):
    chat_id: UUID
    user_id: UUID
    message: str = Field(..., min_length=1, max_length=32000)
    processing_type: Literal["llm", "image"]
    model_id: Optional[str] = "openai_gpt-4o-mini"
    provider_id: Optional[str] = "dalle-3"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4000, ge=1, le=16000)


class MessageAcceptedResponse(BaseModel):
    request_id: UUID
    status: Literal["accepted"] = "accepted"
    message: str = "Запрос принят в обработку"


class MessageResult(BaseModel):
    content: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    model_id: Optional[str] = None
    image_url: Optional[str] = None


class MessageStatusResponse(BaseModel):
    request_id: UUID
    status: Literal["pending", "processing", "done", "failed"]
    result: Optional[MessageResult] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    costs_summary: Optional[dict[str, float]] = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    details: Optional[dict[str, str]] = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[dict[str, Any]] = None


class ServicesStatusResponse(BaseModel):
    gateway: str
    llm: str
    image: str
    cost: str
