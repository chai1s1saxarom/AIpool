"""
Модуль-заглушка для микросервиса генерации изображений.
Реализует OpenAPI спецификацию Image Processing Service.
"""
from datetime import datetime
from typing import Optional, List, Dict
from uuid import uuid4, UUID
import time

from fastapi import FastAPI, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel, Field
from enum import Enum

# ---------- Модели данных ----------
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

class ImageJobCreatedResponse(BaseModel):
    job_id: UUID
    user_request_id: UUID
    status: str = "accepted"
    message: str = "Задача принята в обработку"

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
    job_id: UUID
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

class ImageJobListResponse(BaseModel):
    items: List[ImageJobResponse]
    total: int
    limit: int
    offset: int

class ImageInfo(BaseModel):
    image_id: UUID
    image_url: str
    s3_key: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    size_bytes: Optional[int] = None
    prompt: Optional[str] = None
    provider_id: Optional[ProviderId] = None
    created_at: datetime

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

# ---------- "База данных" в памяти ----------
jobs_db: Dict[UUID, ImageJobResponse] = {}
images_db: Dict[UUID, ImageInfo] = {}

# Статичные данные о провайдерах
PROVIDERS = {
    "dalle-3": ProviderInfo(
        provider_id=ProviderId.dalle3,
        display_name="DALL-E 3",
        description="OpenAI DALL-E 3 model",
        supported_operations=[OperationType.generate, OperationType.edit, OperationType.variation],
        supported_sizes=[ImageSize.s1024, ImageSize.s1024x1792, ImageSize.s1792x1024],
        max_prompt_length=4000,
        price_per_image=0.04
    ),
    "kandinsky": ProviderInfo(
        provider_id=ProviderId.kandinsky,
        display_name="Kandinsky 3.0",
        description="Kandinsky 3.0 from Sber",
        supported_operations=[OperationType.generate],
        supported_sizes=[ImageSize.s512, ImageSize.s1024],
        max_prompt_length=2000,
        price_per_image=0.02
    ),
    "yandexart": ProviderInfo(
        provider_id=ProviderId.yandexart,
        display_name="YandexART",
        description="YandexART model",
        supported_operations=[OperationType.generate, OperationType.edit],
        supported_sizes=[ImageSize.s256, ImageSize.s512, ImageSize.s1024],
        max_prompt_length=3000,
        price_per_image=0.03
    )
}

# Вспомогательная функция для имитации генерации изображения
def generate_mock_image(job: CreateImageJobRequest) -> ImageJobResult:
    # Генерируем фиктивные данные изображения
    image_id = uuid4()
    # URL может указывать на локальный сервер или заглушку
    image_url = f"http://localhost:8002/images/{image_id}/file"  # не реализовано, просто строка
    # Определяем размеры из строки типа "1024x1024"
    if job.size:
        w, h = map(int, job.size.split('x'))
    else:
        w, h = 1024, 1024
    return ImageJobResult(
        image_id=image_id,
        image_url=image_url,
        s3_key=f"images/{image_id}.png",
        width=w,
        height=h,
        format="png",
        size_bytes=w * h * 3,  # грубо
        cost_usd=PROVIDERS[job.provider_id.value].price_per_image
    )

def process_job_background(job_id: UUID, job_data: CreateImageJobRequest):
    """Фоновая задача, эмулирующая обработку"""
    # Обновляем статус на processing
    if job_id in jobs_db:
        jobs_db[job_id].status = JobStatus.processing
        # Имитация длительной работы
        time.sleep(2)  # блокирующая задержка — в реальном проекте использовать asyncio.sleep
        try:
            result = generate_mock_image(job_data)
            # Сохраняем изображение в базу
            image_info = ImageInfo(
                image_id=result.image_id,
                image_url=result.image_url,
                s3_key=result.s3_key,
                width=result.width,
                height=result.height,
                format=result.format,
                size_bytes=result.size_bytes,
                prompt=job_data.prompt,
                provider_id=job_data.provider_id,
                created_at=datetime.now()
            )
            images_db[result.image_id] = image_info

            jobs_db[job_id].status = JobStatus.done
            jobs_db[job_id].result = result
            jobs_db[job_id].finished_at = datetime.now()
            jobs_db[job_id].processing_time_ms = 2000  # фиктивное время
        except Exception as e:
            jobs_db[job_id].status = JobStatus.failed
            jobs_db[job_id].error_message = str(e)
            jobs_db[job_id].finished_at = datetime.now()

# ---------- Приложение FastAPI ----------
app = FastAPI(
    title="Image Processing Service",
    description="Сервис генерации и редактирования изображений (учебная реализация)",
    version="1.0.0"
)

# ---------- Эндпоинты ----------
@app.get("/v1/images/jobs", response_model=ImageJobListResponse, tags=["images"])
def list_image_jobs(
    user_request_id: Optional[UUID] = Query(None),
    status: Optional[JobStatus] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    items = list(jobs_db.values())
    if user_request_id:
        items = [j for j in items if j.user_request_id == user_request_id]
    if status:
        items = [j for j in items if j.status == status]

    # сортировка по created_at убывание
    items.sort(key=lambda x: x.created_at, reverse=True)
    total = len(items)
    page = items[offset:offset+limit]
    return ImageJobListResponse(items=page, total=total, limit=limit, offset=offset)

@app.post("/v1/images/jobs", response_model=ImageJobCreatedResponse, status_code=202, tags=["images"])
def create_image_job(job: CreateImageJobRequest, background_tasks: BackgroundTasks):
    # Валидация провайдера и операции (упрощённо)
    if job.provider_id.value not in PROVIDERS:
        raise HTTPException(status_code=422, detail=ErrorResponse(
            error="UNKNOWN_PROVIDER",
            message=f"Провайдер {job.provider_id} не поддерживается"
        ).dict())

    provider = PROVIDERS[job.provider_id.value]
    if job.operation not in provider.supported_operations:
        raise HTTPException(status_code=422, detail=ErrorResponse(
            error="UNSUPPORTED_OPERATION",
            message=f"Операция {job.operation} не поддерживается провайдером {job.provider_id}"
        ).dict())

    # Создаём запись задачи
    job_id = uuid4()
    now = datetime.now()
    job_entry = ImageJobResponse(
        job_id=job_id,
        user_request_id=job.user_request_id,
        provider_id=job.provider_id,
        operation=job.operation,
        prompt=job.prompt,
        status=JobStatus.pending,
        created_at=now,
        finished_at=None,
        result=None
    )
    jobs_db[job_id] = job_entry

    # Добавляем фоновую задачу для обработки
    background_tasks.add_task(process_job_background, job_id, job)

    return ImageJobCreatedResponse(
        job_id=job_id,
        user_request_id=job.user_request_id
    )

@app.get("/v1/images/jobs/{job_id}", response_model=ImageJobResponse, tags=["images"])
def get_image_job(job_id: UUID = Path(..., description="UUID задачи")):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Задача не найдена"
        ).dict())
    return jobs_db[job_id]

@app.delete("/v1/images/jobs/{job_id}", response_model=ImageJobResponse, tags=["images"])
def cancel_image_job(job_id: UUID = Path(...)):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Задача не найдена"
        ).dict())
    job = jobs_db[job_id]
    if job.status not in [JobStatus.pending, JobStatus.processing]:
        raise HTTPException(status_code=409, detail=ErrorResponse(
            error="JOB_COMPLETED",
            message="Задача уже завершена и не может быть отменена"
        ).dict())
    job.status = JobStatus.cancelled
    job.finished_at = datetime.now()
    return job

@app.get("/v1/images/{image_id}", response_model=ImageInfo, tags=["images"])
def get_image(image_id: UUID = Path(...)):
    if image_id not in images_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Изображение не найдено"
        ).dict())
    return images_db[image_id]

@app.delete("/v1/images/{image_id}", status_code=204, tags=["images"])
def delete_image(image_id: UUID = Path(...)):
    if image_id not in images_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Изображение не найдено"
        ).dict())
    del images_db[image_id]
    # Также можно удалить связанные задачи? Не требуется по спецификации.

@app.get("/v1/providers", response_model=ProviderListResponse, tags=["providers"])
def list_providers():
    return ProviderListResponse(providers=list(PROVIDERS.values()))

@app.get("/v1/providers/{provider_id}", response_model=ProviderInfo, tags=["providers"])
def get_provider(provider_id: ProviderId = Path(...)):
    if provider_id.value not in PROVIDERS:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Провайдер не найден"
        ).dict())
    return PROVIDERS[provider_id.value]

@app.get("/v1/health/liveness", response_model=HealthResponse, tags=["health"])
def health_liveness():
    return HealthResponse(status="healthy", details={"database": "ok", "rabbitmq": "ok", "s3": "ok"})

@app.get("/v1/health/readiness", response_model=HealthResponse, tags=["health"])
def health_readiness():
    # Здесь можно проверить доступность зависимостей, но в заглушке всегда true
    return HealthResponse(status="healthy", details={"database": "ok", "rabbitmq": "ok", "s3": "ok"})