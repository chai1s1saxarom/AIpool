from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Any
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Provider(str, Enum):
    openai = "openai"
    google = "google"
    anthropic = "anthropic"


class LLMMessage(BaseModel):
    role: MessageRole
    content: str = Field(..., min_length=1)


class CreateLLMJobRequest(BaseModel):
    messages: List[LLMMessage] = Field(..., min_length=1)
    user_request_id: str
    llm_model_id: str
    consumer_service_id: str
    webhook_url: Optional[str] = None
    timeout: int = Field(default=120, ge=10, le=600)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, ge=1, le=128000)
    structured_output: bool = False


class LLMResult(BaseModel):
    response: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float


class LLMJobCreatedResponse(BaseModel):
    job_id: str
    user_request_id: str
    status: Literal["accepted"] = "accepted"
    message: str = "Задача принята в обработку"


class LLMJobResponse(BaseModel):
    job_id: str
    user_request_id: str
    llm_model_id: Optional[str] = None
    consumer_service_id: Optional[str] = None
    status: JobStatus
    result: Optional[LLMResult] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LLMJobListResponse(BaseModel):
    items: List[LLMJobResponse]
    total: int
    limit: int
    offset: int


class LLMTraceResponse(BaseModel):
    user_request_id: str
    jobs: List[LLMJobResponse]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


class ModelInfo(BaseModel):
    model_id: str
    provider: Provider
    display_name: str
    description: Optional[str] = None
    max_context_tokens: int
    max_output_tokens: int
    input_price_per_million: float
    output_price_per_million: float
    supports_structured_output: bool = True


class ModelListResponse(BaseModel):
    models: List[ModelInfo]


class HealthDetails(BaseModel):
    database: Literal["ok", "error"]
    rabbitmq: Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    details: Optional[HealthDetails] = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
