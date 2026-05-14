from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from enum import Enum

# ---------- Перечисления ----------
class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"

class OperationType(str, Enum):
    generate = "generate"
    edit = "edit"
    variation = "variation"

class ProviderId(str, Enum):
    dalle3 = "dalle-3"
    kandinsky = "kandinsky"
    yandexart = "yandexart"

class ImageSize(str, Enum):
    s256 = "256x256"
    s512 = "512x512"
    s1024 = "1024x1024"
    s1024x1792 = "1024x1792"
    s1792x1024 = "1792x1024"

class ImageQuality(str, Enum):
    standard = "standard"
    hd = "hd"

class Style(str, Enum):
    vivid = "vivid"
    natural = "natural"

# ---------- Модели запросов ----------
class CreateImageJobRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: Optional[str] = Field(None, max_length=2000)
    user_request_id: UUID
    consumer_service_id: str
    provider_id: ProviderId = ProviderId.dalle3
    operation: OperationType = OperationType.generate
    source_image_url: Optional[str] = None
    size: ImageSize = ImageSize.s1024
    quality: ImageQuality = ImageQuality.standard
    style: Style = Style.vivid
    webhook_url: Optional[str] = None


class UpdateImageJobRequest(BaseModel):
    """Частичное обновление задачи (только в статусе pending)."""

    prompt: Optional[str] = Field(None, min_length=1, max_length=4000)
    provider_id: Optional[ProviderId] = None
    operation: Optional[OperationType] = None


class UpdateImageInfoRequest(BaseModel):
    image_url: Optional[str] = Field(None, max_length=500)
    prompt: Optional[str] = Field(None, max_length=4000)
    provider_id: Optional[ProviderId] = None


class CreateImageInfoRequest(BaseModel):
    image_url: str = Field(..., max_length=500)
    prompt: Optional[str] = Field(None, max_length=4000)
    provider_id: Optional[ProviderId] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = Field(None, max_length=20)
    size_bytes: Optional[int] = None
    s3_key: Optional[str] = Field(None, max_length=200)

# ---------- Модели ответов ----------
class ImageJobResult(BaseModel):
    image_id: UUID
    image_url: str
    s3_key: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    size_bytes: Optional[int] = None
    cost_usd: float

class ImageJobResponse(BaseModel):
    job_id: UUID = Field(validation_alias="id", serialization_alias="job_id")
    user_request_id: UUID
    provider_id: Optional[ProviderId] = None
    operation: OperationType
    prompt: str
    status: JobStatus
    result: Optional[ImageJobResult] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

class ImageJobCreatedResponse(BaseModel):
    job_id: UUID
    user_request_id: UUID
    status: str = "accepted"
    message: str = "Задача принята в обработку"

class ImageJobListResponse(BaseModel):
    items: List[ImageJobResponse]
    total: int
    limit: int
    offset: int


class ImageInfo(BaseModel):
    image_id: UUID = Field(validation_alias="id", serialization_alias="image_id")
    image_url: str
    s3_key: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    size_bytes: Optional[int] = None
    prompt: Optional[str] = None
    provider_id: Optional[ProviderId] = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


class ImageInfoListResponse(BaseModel):
    items: List[ImageInfo]
    total: int
    limit: int
    offset: int


class ProviderInfo(BaseModel):
    provider_id: ProviderId
    display_name: str
    description: Optional[str] = None
    supported_operations: List[OperationType]
    supported_sizes: List[ImageSize]
    max_prompt_length: int = 4000
    price_per_image: float

class ProviderListResponse(BaseModel):
    providers: List[ProviderInfo]

class HealthResponse(BaseModel):
    status: str
    details: Optional[dict] = None

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[dict] = None


class LogEntry(BaseModel):
    id: UUID
    action: str
    message: str
    user_request_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalPostResponse(BaseModel):
    userId: int
    id: int
    title: str
    body: str


class AggregatedExternalResponse(BaseModel):
    posts_sample: Optional[dict] = None
    users_sample: Optional[dict] = None
    todos_sample: Optional[dict] = None
    errors: Optional[List[str]] = None


class RabbitMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class RabbitMessageResponse(BaseModel):
    status: str = "sent"
    queue: str