import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID, uuid4

import httpx
import pika
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import AsyncSessionLocal, get_db

RABBIT_QUEUE_NAME = "lab_queue"


def generate_mock_image(job_data: schemas.CreateImageJobRequest) -> schemas.ImageJobResult:
    image_id = uuid4()
    image_url = f"http://localhost:8002/images/{image_id}/file"
    size_str = job_data.size.value
    w, h = map(int, size_str.split("x"))
    price_per_image = 0.04
    return schemas.ImageJobResult(
        image_id=image_id,
        image_url=image_url,
        s3_key=f"images/{image_id}.png",
        width=w,
        height=h,
        format="png",
        size_bytes=w * h * 3,
        cost_usd=price_per_image,
    )


async def process_job_background(job_id: UUID, job_data: schemas.CreateImageJobRequest) -> None:
    async with AsyncSessionLocal() as db:
        db_job = await db.get(models.Job, job_id)
        if not db_job:
            return
        try:
            db_job.status = schemas.JobStatus.processing.value
            await db.commit()

            await asyncio.sleep(2)

            result = generate_mock_image(job_data)
            db_image = models.ImageInfo(
                id=result.image_id,
                image_url=result.image_url,
                s3_key=result.s3_key,
                width=result.width,
                height=result.height,
                format=result.format,
                size_bytes=result.size_bytes,
                prompt=job_data.prompt,
                provider_id=job_data.provider_id.value,
            )
            db.add(db_image)

            db_job.status = schemas.JobStatus.done.value
            db_job.result_image_id = result.image_id
            db_job.finished_at = datetime.now()
            db_job.processing_time_ms = 2000
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            db_job = await db.get(models.Job, job_id)
            if db_job:
                db_job.status = schemas.JobStatus.failed.value
                db_job.error_message = str(e)
                db_job.finished_at = datetime.now()
                await db.commit()


async def persist_user_action_log(
    action: str,
    message: str,
    user_request_id: Optional[UUID],
    job_id: Optional[UUID],
) -> None:
    started = time.perf_counter()
    async with AsyncSessionLocal() as db:
        log_row = models.Log(
            action=action,
            message=message,
            user_request_id=user_request_id,
            job_id=job_id,
            duration_ms=None,
        )
        db.add(log_row)
        await db.flush()
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_row.duration_ms = duration_ms
        await db.commit()


def _publish_rabbitmq_sync(message: str) -> None:
    url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5673/")
    params = pika.URLParameters(url)
    conn = pika.BlockingConnection(params)
    try:
        channel = conn.channel()
        channel.queue_declare(queue=RABBIT_QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=RABBIT_QUEUE_NAME,
            body=message.encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    finally:
        conn.close()


def get_http_client(request: Request) -> httpx.AsyncClient:
    if not hasattr(request.app.state, "http_client"):
        timeout = httpx.Timeout(10.0, connect=5.0)
        request.app.state.http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    return request.app.state.http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(10.0, connect=5.0)
    app.state.http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Image Processing Service",
    description="Сервис генерации и редактирования изображений (async SQLAlchemy + PostgreSQL)",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/v1/images/jobs", response_model=schemas.ImageJobListResponse)
async def list_image_jobs(
    user_request_id: Optional[UUID] = None,
    status: Optional[schemas.JobStatus] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(models.Job)
    count_stmt = select(func.count()).select_from(models.Job)
    if user_request_id is not None:
        stmt = stmt.where(models.Job.user_request_id == user_request_id)
        count_stmt = count_stmt.where(models.Job.user_request_id == user_request_id)
    if status is not None:
        stmt = stmt.where(models.Job.status == status.value)
        count_stmt = count_stmt.where(models.Job.status == status.value)

    total = await db.scalar(count_stmt) or 0
    stmt = stmt.order_by(models.Job.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    return schemas.ImageJobListResponse(
        items=jobs,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post("/v1/images/jobs", response_model=schemas.ImageJobCreatedResponse, status_code=202)
async def create_image_job(
    job: schemas.CreateImageJobRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    providers = ["dalle-3", "kandinsky", "yandexart"]
    if job.provider_id.value not in providers:
        raise HTTPException(status_code=422, detail={"error": "UNKNOWN_PROVIDER"})

    db_job = models.Job(
        id=uuid4(),
        user_request_id=job.user_request_id,
        provider_id=job.provider_id.value,
        operation=job.operation.value,
        prompt=job.prompt,
        status=schemas.JobStatus.pending.value,
    )
    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)

    background_tasks.add_task(
        persist_user_action_log,
        "create_job",
        f"Создана задача генерации, provider={job.provider_id.value}",
        job.user_request_id,
        db_job.id,
    )
    if not os.getenv("SKIP_JOB_PROCESSING"):
        background_tasks.add_task(process_job_background, db_job.id, job)

    return schemas.ImageJobCreatedResponse(job_id=db_job.id, user_request_id=job.user_request_id)


@app.get("/v1/images/jobs/{job_id}", response_model=schemas.ImageJobResponse)
async def get_image_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    db_job = await db.get(models.Job, job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    return db_job


@app.put("/v1/images/jobs/{job_id}", response_model=schemas.ImageJobResponse)
async def update_image_job(
    job_id: UUID,
    body: schemas.UpdateImageJobRequest,
    db: AsyncSession = Depends(get_db),
):
    db_job = await db.get(models.Job, job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if db_job.status != schemas.JobStatus.pending.value:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_STATE", "message": "Обновление доступно только для задач в статусе pending"},
        )
    if body.prompt is None and body.provider_id is None and body.operation is None:
        raise HTTPException(status_code=422, detail={"error": "EMPTY_UPDATE"})

    if body.prompt is not None:
        db_job.prompt = body.prompt
    if body.provider_id is not None:
        db_job.provider_id = body.provider_id.value
    if body.operation is not None:
        db_job.operation = body.operation.value

    await db.commit()
    await db.refresh(db_job)
    return db_job


@app.delete("/v1/images/jobs/{job_id}", response_model=schemas.ImageJobResponse)
async def cancel_image_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    db_job = await db.get(models.Job, job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if db_job.status not in (schemas.JobStatus.pending.value, schemas.JobStatus.processing.value):
        raise HTTPException(status_code=409, detail={"error": "JOB_COMPLETED"})
    db_job.status = schemas.JobStatus.cancelled.value
    db_job.finished_at = datetime.now()
    await db.commit()
    await db.refresh(db_job)
    return db_job


@app.get("/v1/images", response_model=schemas.ImageInfoListResponse)
async def list_images(limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(models.ImageInfo)) or 0
    stmt = select(models.ImageInfo).order_by(models.ImageInfo.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return schemas.ImageInfoListResponse(items=rows, total=total, limit=limit, offset=offset)


@app.post("/v1/images", response_model=schemas.ImageInfo, status_code=201)
async def create_image(body: schemas.CreateImageInfoRequest, db: AsyncSession = Depends(get_db)):
    img = models.ImageInfo(
        id=uuid4(),
        image_url=body.image_url,
        s3_key=body.s3_key,
        width=body.width,
        height=body.height,
        format=body.format,
        size_bytes=body.size_bytes,
        prompt=body.prompt,
        provider_id=body.provider_id.value if body.provider_id else None,
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)
    return img


@app.get("/v1/images/{image_id}", response_model=schemas.ImageInfo)
async def get_image(image_id: UUID, db: AsyncSession = Depends(get_db)):
    db_image = await db.get(models.ImageInfo, image_id)
    if not db_image:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    return db_image


@app.put("/v1/images/{image_id}", response_model=schemas.ImageInfo)
async def update_image(
    image_id: UUID,
    body: schemas.UpdateImageInfoRequest,
    db: AsyncSession = Depends(get_db),
):
    db_image = await db.get(models.ImageInfo, image_id)
    if not db_image:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    if body.image_url is None and body.prompt is None and body.provider_id is None:
        raise HTTPException(status_code=422, detail={"error": "EMPTY_UPDATE"})
    if body.image_url is not None:
        db_image.image_url = body.image_url
    if body.prompt is not None:
        db_image.prompt = body.prompt
    if body.provider_id is not None:
        db_image.provider_id = body.provider_id.value
    await db.commit()
    await db.refresh(db_image)
    return db_image


@app.delete("/v1/images/{image_id}", status_code=204)
async def delete_image(image_id: UUID, db: AsyncSession = Depends(get_db)):
    db_image = await db.get(models.ImageInfo, image_id)
    if not db_image:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    await db.delete(db_image)
    await db.commit()
    return None


@app.get("/v1/external/posts/{post_id}", response_model=schemas.ExternalPostResponse)
async def get_external_post(
    post_id: int,
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
):
    url = f"https://jsonplaceholder.typicode.com/posts/{post_id}"
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail={"error": "UPSTREAM_HTTP_ERROR", "status": e.response.status_code},
        ) from e
    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail={"error": "UPSTREAM_TIMEOUT"}) from e
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail={"error": "UPSTREAM_REQUEST_ERROR", "message": str(e)}) from e


async def _fetch_json(client: httpx.AsyncClient, url: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        r = await client.get(url)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:  # noqa: BLE001
        return None, f"{url}: {type(e).__name__}: {e}"


@app.get("/v1/external/aggregate", response_model=schemas.AggregatedExternalResponse)
async def aggregate_external(
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
):
    urls = {
        "posts_sample": "https://jsonplaceholder.typicode.com/posts/1",
        "users_sample": "https://jsonplaceholder.typicode.com/users/1",
        "todos_sample": "https://jsonplaceholder.typicode.com/todos/1",
    }
    keys = list(urls.keys())
    results = await asyncio.gather(*[_fetch_json(client, urls[k]) for k in keys])
    errors: list[str] = []
    payload: dict[str, Optional[dict]] = {}
    for key, (data, err) in zip(keys, results, strict=True):
        if err:
            errors.append(err)
        else:
            payload[key] = data
    return schemas.AggregatedExternalResponse(
        posts_sample=payload.get("posts_sample"),
        users_sample=payload.get("users_sample"),
        todos_sample=payload.get("todos_sample"),
        errors=errors or None,
    )


@app.post("/v1/rabbit/messages", response_model=schemas.RabbitMessageResponse)
async def send_rabbit_message(msg: schemas.RabbitMessageRequest):
    try:
        await asyncio.to_thread(_publish_rabbitmq_sync, msg.text)
    except pika.exceptions.AMQPError as e:
        raise HTTPException(status_code=502, detail={"error": "RABBITMQ_ERROR", "message": str(e)}) from e
    return schemas.RabbitMessageResponse(queue=RABBIT_QUEUE_NAME)


@app.get("/v1/logs", response_model=list[schemas.LogEntry])
async def list_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = select(models.Log).order_by(models.Log.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@app.get("/v1/providers", response_model=schemas.ProviderListResponse)
async def list_providers():
    from app.schemas import ImageSize, OperationType, ProviderId, ProviderInfo

    providers = [
        ProviderInfo(
            provider_id=ProviderId.dalle3,
            display_name="DALL-E 3",
            description="OpenAI DALL-E 3 model",
            supported_operations=[OperationType.generate, OperationType.edit, OperationType.variation],
            supported_sizes=[ImageSize.s1024, ImageSize.s1024x1792, ImageSize.s1792x1024],
            max_prompt_length=4000,
            price_per_image=0.04,
        ),
        ProviderInfo(
            provider_id=ProviderId.kandinsky,
            display_name="Kandinsky 3.0",
            description="Kandinsky 3.0 from Sber",
            supported_operations=[OperationType.generate],
            supported_sizes=[ImageSize.s512, ImageSize.s1024],
            max_prompt_length=2000,
            price_per_image=0.02,
        ),
        ProviderInfo(
            provider_id=ProviderId.yandexart,
            display_name="YandexART",
            description="YandexART model",
            supported_operations=[OperationType.generate, OperationType.edit],
            supported_sizes=[ImageSize.s256, ImageSize.s512, ImageSize.s1024],
            max_prompt_length=3000,
            price_per_image=0.03,
        ),
    ]
    return schemas.ProviderListResponse(providers=providers)


@app.get("/v1/providers/{provider_id}", response_model=schemas.ProviderInfo)
async def get_provider(provider_id: schemas.ProviderId):
    from app.schemas import ImageSize, OperationType, ProviderInfo

    if provider_id == schemas.ProviderId.dalle3:
        return ProviderInfo(
            provider_id=schemas.ProviderId.dalle3,
            display_name="DALL-E 3",
            description="OpenAI DALL-E 3 model",
            supported_operations=[OperationType.generate, OperationType.edit, OperationType.variation],
            supported_sizes=[ImageSize.s1024, ImageSize.s1024x1792, ImageSize.s1792x1024],
            max_prompt_length=4000,
            price_per_image=0.04,
        )
    if provider_id == schemas.ProviderId.kandinsky:
        return ProviderInfo(
            provider_id=schemas.ProviderId.kandinsky,
            display_name="Kandinsky 3.0",
            description="Kandinsky 3.0 from Sber",
            supported_operations=[OperationType.generate],
            supported_sizes=[ImageSize.s512, ImageSize.s1024],
            max_prompt_length=2000,
            price_per_image=0.02,
        )
    if provider_id == schemas.ProviderId.yandexart:
        return ProviderInfo(
            provider_id=schemas.ProviderId.yandexart,
            display_name="YandexART",
            description="YandexART model",
            supported_operations=[OperationType.generate, OperationType.edit],
            supported_sizes=[ImageSize.s256, ImageSize.s512, ImageSize.s1024],
            max_prompt_length=3000,
            price_per_image=0.03,
        )
    raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})


@app.get("/v1/health/liveness", response_model=schemas.HealthResponse)
async def health_liveness():
    return schemas.HealthResponse(status="healthy", details={"database": "ok"})


@app.get("/v1/health/readiness", response_model=schemas.HealthResponse)
async def health_readiness(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return schemas.HealthResponse(
        status="healthy" if db_ok else "unhealthy",
        details={"database": "ok" if db_ok else "error"},
    )
