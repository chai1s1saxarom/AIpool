"""
Модуль для микросервиса учёта затрат.
Реализует OpenAPI спецификацию Cost Accounting Service с асинхронными операциями.
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
from uuid import uuid4, UUID
import time

from fastapi import FastAPI, HTTPException, Query, Path, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app import models, schemas, crud
from app.database import engine, get_db
from app.external_api import get_exchange_rates_api, get_exchange_rates_history, get_consolidated_financial_data
from app.background_tasks import log_to_file, update_exchange_rates, analytics_log
from app.rabbit_publisher import publish_cost_event

# Создаем таблицы в БД если их нет (для разработки)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cost Accounting Service",
    description="Сервис учёта затрат на использование AI-сервисов с поддержкой асинхронных вызовов",
    version="1.0.0"
)

# Модель цен для различных LLM-моделей (USD за 1000 токенов)
MODEL_PRICES = {
    "openai_gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai_gpt-4o": {"input": 5.00, "output": 15.00},
    "yandexgpt": {"input": 1.00, "output": 3.00},
}

# Вспомогательные функции
def get_current_rates(db: Session) -> tuple[float, float]:
    """Возвращает последние актуальные курсы USD/RUB и EUR/RUB"""
    latest = crud.get_latest_exchange_rate(db)
    if latest:
        return latest.usd_rub, latest.eur_rub
    return 90.0, 100.0  # fallback

def convert_amount(amount: float, from_currency: schemas.Currency, usd_rate: float, eur_rate: float) -> dict:
    """Конвертирует сумму из исходной валюты в RUB, USD, EUR."""
    if from_currency == schemas.Currency.RUB:
        rub = amount
        usd = amount / usd_rate
        eur = amount / eur_rate
    elif from_currency == schemas.Currency.USD:
        usd = amount
        rub = amount * usd_rate
        eur = amount * (usd_rate / eur_rate)
    else:  # EUR
        eur = amount
        rub = amount * eur_rate
        usd = amount * (eur_rate / usd_rate)
    return {
        "rub": round(rub, 2),
        "usd": round(usd, 4),
        "eur": round(eur, 4),
        "usd_rate": usd_rate,
        "eur_rate": eur_rate
    }

# Эндпоинты для учета затрат
@app.get("/", tags=["root"])
def root():
    """Корневой эндпоинт для проверки работоспособности"""
    return {
        "service": "Cost Accounting Service",
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs"
    }

@app.get("/v1/costs", response_model=schemas.CostRecordListResponse, tags=["costs"])
def list_costs(
        user_request_id: Optional[UUID] = Query(None),
        service_name: Optional[str] = Query(None),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db)
):
    """
    Получить список всех записей о затратах с возможностью фильтрации
    и пагинацией.
    """
    return crud.get_cost_records(
        db,
        user_request_id=user_request_id,
        service_name=service_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset
    )


# ИСПРАВЛЕНО: был потерян декоратор @app.post — эндпоинт не был зарегистрирован!
@app.post("/v1/costs", response_model=schemas.CostRecordResponse, status_code=201, tags=["costs"])
def create_cost_record(
        record: schemas.CreateCostRecordRequest,
        background_tasks: BackgroundTasks,  # Просто тип, без Depends()
        db: Session = Depends(get_db)
):

    """
    Создать новую запись о затратах с указанием суммы вручную.

    Автоматически конвертирует сумму в другие валюты по актуальному курсу.
    """
    start_time = time.time()

    usd_rate, eur_rate = get_current_rates(db)
    converted = convert_amount(record.amount, record.currency, usd_rate, eur_rate)

    result = crud.create_cost_record(db, record, converted)

    # Добавляем фоновую задачу для логирования
    execution_time = int((time.time() - start_time) * 1000)
    background_tasks.add_task(
        analytics_log,
        record.user_request_id,
        "create_cost_record",
        execution_time
    )
    background_tasks.add_task(
        log_to_file,
        f"Cost record created: {record.service_name}, amount: {record.amount} {record.currency}"
    )

    # Публикуем событие в RabbitMQ — в фоне, чтобы не задерживать HTTP-ответ
    background_tasks.add_task(
        publish_cost_event,
        "cost_record_created",
        {
            "id": str(result.id),
            "service_name": result.service_name,
            "user_request_id": str(result.user_request_id),
            "job_id": result.job_id,
            "currency": str(record.currency),
            "usd_amount": result.usd_amount,
            "rub_amount": result.rub_amount,
            "eur_amount": result.eur_amount,
            "created_at": result.created_at.isoformat()
        }
    )

    return result

@app.post("/v2/costs", response_model=schemas.CostRecordResponse, status_code=201, tags=["costs"])
def create_cost_record_v2(
        record: schemas.CreateCostRecordV2Request,
        background_tasks: BackgroundTasks, # Добавляем Depends()
        db: Session = Depends(get_db)
):
    """
    Создать запись о затратах с автоматическим расчётом стоимости по токенам.

    Стоимость рассчитывается по формуле:
    `(input_tokens * input_price) + (output_tokens * output_price)`

    Цены берутся из справочника по `model_id`.
    """
    if record.model_id not in MODEL_PRICES:
        raise HTTPException(status_code=422, detail={"error": "UNKNOWN_MODEL", "message": f"Модель {record.model_id} не найдена в справочнике"})

    start_time = time.time()

    prices = MODEL_PRICES[record.model_id]
    # расчёт в USD
    cost_usd = (record.prompt_tokens / 1000) * prices["input"] + (record.completion_tokens / 1000) * prices["output"]

    usd_rate, eur_rate = get_current_rates(db)
    # переводим в рубли и евро
    rub_amount = cost_usd * usd_rate
    eur_amount = cost_usd * (usd_rate / eur_rate)

    # Создаем запись через модель CreateCostRecordRequest
    cost_request = schemas.CreateCostRecordRequest(
        service_name=record.service_name,
        user_request_id=record.user_request_id,
        job_id=record.job_id,
        currency=schemas.Currency.USD,
        amount=cost_usd
    )

    converted = {
        "rub": round(rub_amount, 2),
        "usd": round(cost_usd, 4),
        "eur": round(eur_amount, 4),
        "usd_rate": usd_rate,
        "eur_rate": eur_rate
    }

    result = crud.create_cost_record(db, cost_request, converted)

    # Добавляем фоновую задачу для логирования
    execution_time = int((time.time() - start_time) * 1000)
    background_tasks.add_task(
        analytics_log,
        record.user_request_id,
        "create_cost_record_v2",
        execution_time
    )
    background_tasks.add_task(
        log_to_file,
        f"Cost record created by tokens: {record.service_name}, model: {record.model_id}, "
        f"tokens: {record.prompt_tokens}/{record.completion_tokens}, cost: {cost_usd} USD"
    )

    # Публикуем событие в RabbitMQ с расширенными данными по токенам
    background_tasks.add_task(
        publish_cost_event,
        "cost_record_created_v2",
        {
            "id": str(result.id),
            "service_name": result.service_name,
            "user_request_id": str(result.user_request_id),
            "job_id": result.job_id,
            "model_id": record.model_id,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "usd_amount": result.usd_amount,
            "rub_amount": result.rub_amount,
            "eur_amount": result.eur_amount,
            "created_at": result.created_at.isoformat()
        }
    )

    return result

@app.get("/v1/costs/{cost_id}", response_model=schemas.CostRecordResponse, tags=["costs"])
def get_cost_record(cost_id: UUID = Path(...), db: Session = Depends(get_db)):
    """Получить детальную информацию о записи затрат по ID"""
    record = crud.get_cost_record(db, cost_id)
    if not record:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Запись не найдена"})
    return record

@app.delete("/v1/costs/{cost_id}", status_code=204, tags=["costs"])
def delete_cost_record(cost_id: UUID = Path(...), db: Session = Depends(get_db)):
    """Удалить запись о затратах"""
    success = crud.delete_cost_record(db, cost_id)
    if not success:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Запись не найдена"})
    return None

# Асинхронные эндпоинты для работы с внешними API
@app.get("/v1/exchange-rates/async", tags=["exchange-rates"])
async def get_exchange_rates_async(
        background_tasks: BackgroundTasks,  # Move this before any default arguments
):
    """Асинхронно получает актуальные курсы валют из внешнего API"""
    rates = await get_exchange_rates_api()

    # Добавляем фоновую задачу для обновления курсов в БД
    background_tasks.add_task(update_exchange_rates, rates)

    return rates

@app.get("/v1/exchange-rates/history/async", tags=["exchange-rates"])
async def get_exchange_rates_history_async(
        background_tasks: BackgroundTasks,
        days: int = Query(7, ge=1, le=30)
):
    """Асинхронно получает историю курсов валют за указанное количество дней"""
    rates = await get_exchange_rates_history(days)
    background_tasks.add_task(log_to_file, f"Exchange rates history requested: {days} days")
    return {"rates": rates}

@app.get("/v1/financial-data", tags=["statistics"])
async def get_financial_data():
    """
    Параллельно получает данные из нескольких источников и объединяет их.
    Демонстрирует использование asyncio.gather().
    """
    return await get_consolidated_financial_data()

@app.get("/v1/exchange-rates", response_model=schemas.ExchangeRatesResponse, tags=["exchange-rates"])
def get_exchange_rates(limit: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    """Получить актуальные курсы валют из БД"""
    rates = crud.get_exchange_rates(db, limit)
    return {"rates": rates}

@app.get("/v1/exchange-rates/{date}", response_model=schemas.ExchangeRateResponse, tags=["exchange-rates"])
def get_exchange_rate_by_date(date: date = Path(...), db: Session = Depends(get_db)):
    """Получить курсы валют на указанную дату"""
    rate = crud.get_exchange_rate_by_date(db, date)
    if not rate:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Курс на указанную дату не найден"})
    return rate

# Эндпоинты для проверки здоровья сервиса
@app.get("/v1/health/liveness", response_model=schemas.HealthResponse, tags=["health"])
def health_liveness():
    """Проверка живости сервиса"""
    return schemas.HealthResponse(status="healthy", details={"database": "ok"})

@app.get("/v1/health/readiness", response_model=schemas.HealthResponse, tags=["health"])
def health_readiness(db: Session = Depends(get_db)):
    """Проверка готовности сервиса (проверка подключения к БД)"""
    try:
        # Проверяем подключение к БД
        db.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"

    status = "healthy" if db_status == "ok" else "unhealthy"
    return schemas.HealthResponse(status=status, details={"database": db_status})
