"""
Модуль-заглушка для микросервиса учёта затрат.
Реализует OpenAPI спецификацию Cost Accounting Service.
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
from uuid import uuid4, UUID

from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field
from enum import Enum

# ---------- Модели данных (Pydantic) ----------
class Currency(str, Enum):
    USD = "USD"
    RUB = "RUB"
    EUR = "EUR"

class CreateCostRecordRequest(BaseModel):
    service_name: str
    user_request_id: UUID
    job_id: Optional[str] = None
    currency: Currency
    amount: float = Field(gt=0)

class CreateCostRecordV2Request(BaseModel):
    service_name: str
    user_request_id: UUID
    job_id: Optional[str] = None
    model_id: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)

class CostRecordResponse(BaseModel):
    id: UUID
    service_name: str
    user_request_id: UUID
    job_id: Optional[str]
    currency: Currency            # исходная валюта
    rub_amount: float
    usd_amount: float
    eur_amount: float
    usd_rate: float                # курс USD/RUB на момент создания
    eur_rate: float                # курс EUR/RUB на момент создания
    created_at: datetime

class CostRecordListResponse(BaseModel):
    items: List[CostRecordResponse]
    total: int
    limit: int
    offset: int

class UserRequestCostResponse(BaseModel):
    user_request_id: UUID
    total_rub: float
    total_usd: float
    total_eur: float
    records_count: int

class CostsSummaryResponse(BaseModel):
    period: dict
    total: dict
    breakdown: List[dict]

class ExchangeRateResponse(BaseModel):
    date: date
    usd_rub: float
    eur_rub: float
    eur_usd: Optional[float] = None
    updated_at: datetime

class ExchangeRatesResponse(BaseModel):
    rates: List[ExchangeRateResponse]

class HealthResponse(BaseModel):
    status: str
    details: Optional[dict] = None

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[dict] = None

# ---------- "База данных" в памяти ----------
# Хранилище записей о затратах
costs_db: Dict[UUID, CostRecordResponse] = {}

# Справочник цен моделей (USD за 1000 токенов)
MODEL_PRICES = {
    "openai_gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai_gpt-4o": {"input": 5.00, "output": 15.00},
    "yandexgpt": {"input": 1.00, "output": 3.00},
    # другие модели можно добавить
}

# Хранилище курсов валют (история)
exchange_rates_db: List[ExchangeRateResponse] = []

# Инициализируем несколькими записями для демонстрации
def init_exchange_rates():
    today = date.today()
    for i in range(7):
        day = today - timedelta(days=i)
        # случайные или фиксированные курсы
        rate = ExchangeRateResponse(
            date=day,
            usd_rub=90.0 + i * 0.5,
            eur_rub=100.0 + i * 0.3,
            updated_at=datetime.now() - timedelta(days=i)
        )
        rate.eur_usd = rate.eur_rub / rate.usd_rub
        exchange_rates_db.append(rate)

init_exchange_rates()

# ---------- Приложение FastAPI ----------
app = FastAPI(
    title="Cost Accounting Service",
    description="Сервис учёта затрат на использование AI-сервисов (учебная реализация)",
    version="1.0.0"
)

# ---------- Вспомогательные функции ----------
def get_current_rates() -> tuple[float, float]:
    """Возвращает последние актуальные курсы USD/RUB и EUR/RUB"""
    if exchange_rates_db:
        latest = sorted(exchange_rates_db, key=lambda x: x.date, reverse=True)[0]
        return latest.usd_rub, latest.eur_rub
    return 90.0, 100.0  # fallback

def convert_amount(amount: float, from_currency: Currency, usd_rate: float, eur_rate: float) -> dict:
    """Конвертирует сумму из исходной валюты в RUB, USD, EUR."""
    if from_currency == Currency.RUB:
        rub = amount
        usd = amount / usd_rate
        eur = amount / eur_rate
    elif from_currency == Currency.USD:
        usd = amount
        rub = amount * usd_rate
        eur = amount * (usd_rate / eur_rate)
    else:  # EUR
        eur = amount
        rub = amount * eur_rate
        usd = amount * (eur_rate / usd_rate)
    return {"rub": round(rub, 2), "usd": round(usd, 4), "eur": round(eur, 4)}

def filter_costs(
    user_request_id: Optional[UUID] = None,
    service_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
) -> List[CostRecordResponse]:
    """Фильтрация записей по параметрам"""
    items = list(costs_db.values())
    if user_request_id:
        items = [c for c in items if c.user_request_id == user_request_id]
    if service_name:
        items = [c for c in items if c.service_name == service_name]
    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time())
        items = [c for c in items if c.created_at >= dt_from]
    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time())
        items = [c for c in items if c.created_at <= dt_to]
    return items

# ---------- Эндпоинты ----------
@app.get("/v1/costs", response_model=CostRecordListResponse, tags=["costs"])
def list_costs(
    user_request_id: Optional[UUID] = Query(None),
    service_name: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    filtered = filter_costs(user_request_id, service_name, date_from, date_to)
    total = len(filtered)
    items = filtered[offset:offset + limit]
    return CostRecordListResponse(items=items, total=total, limit=limit, offset=offset)

@app.post("/v1/costs", response_model=CostRecordResponse, status_code=201, tags=["costs"])
def create_cost_record(record: CreateCostRecordRequest):
    usd_rate, eur_rate = get_current_rates()
    converted = convert_amount(record.amount, record.currency, usd_rate, eur_rate)

    new_id = uuid4()
    now = datetime.now()
    cost_record = CostRecordResponse(
        id=new_id,
        service_name=record.service_name,
        user_request_id=record.user_request_id,
        job_id=record.job_id,
        currency=record.currency,
        rub_amount=converted["rub"],
        usd_amount=converted["usd"],
        eur_amount=converted["eur"],
        usd_rate=usd_rate,
        eur_rate=eur_rate,
        created_at=now
    )
    costs_db[new_id] = cost_record
    return cost_record

@app.post("/v2/costs", response_model=CostRecordResponse, status_code=201, tags=["costs"])
def create_cost_record_v2(record: CreateCostRecordV2Request):
    if record.model_id not in MODEL_PRICES:
        raise HTTPException(status_code=422, detail=ErrorResponse(
            error="UNKNOWN_MODEL",
            message=f"Модель {record.model_id} не найдена в справочнике"
        ).dict())

    prices = MODEL_PRICES[record.model_id]
    # расчёт в USD
    cost_usd = (record.prompt_tokens / 1000) * prices["input"] + (record.completion_tokens / 1000) * prices["output"]

    usd_rate, eur_rate = get_current_rates()
    # переводим в рубли и евро
    rub_amount = cost_usd * usd_rate
    eur_amount = cost_usd * (usd_rate / eur_rate)  # или cost_usd * usd_rate / eur_rate?

    new_id = uuid4()
    now = datetime.now()
    cost_record = CostRecordResponse(
        id=new_id,
        service_name=record.service_name,
        user_request_id=record.user_request_id,
        job_id=record.job_id,
        currency=Currency.USD,   # исходная валюта расчёта — USD
        rub_amount=round(rub_amount, 2),
        usd_amount=round(cost_usd, 4),
        eur_amount=round(eur_amount, 4),
        usd_rate=usd_rate,
        eur_rate=eur_rate,
        created_at=now
    )
    costs_db[new_id] = cost_record
    return cost_record

@app.get("/v1/costs/{cost_id}", response_model=CostRecordResponse, tags=["costs"])
def get_cost_record(cost_id: UUID = Path(..., description="UUID записи")):
    if cost_id not in costs_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Запись не найдена"
        ).dict())
    return costs_db[cost_id]

@app.delete("/v1/costs/{cost_id}", status_code=204, tags=["costs"])
def delete_cost_record(cost_id: UUID = Path(...)):
    if cost_id not in costs_db:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Запись не найдена"
        ).dict())
    del costs_db[cost_id]

@app.get("/v1/costs/user-request/{user_request_id}", response_model=UserRequestCostResponse, tags=["statistics"])
def get_user_request_cost(user_request_id: UUID = Path(...)):
    records = filter_costs(user_request_id=user_request_id)
    if not records:
        raise HTTPException(status_code=404, detail=ErrorResponse(
            error="NOT_FOUND",
            message="Записи не найдены"
        ).dict())

    total_rub = sum(r.rub_amount for r in records)
    total_usd = sum(r.usd_amount for r in records)
    total_eur = sum(r.eur_amount for r in records)
    return UserRequestCostResponse(
        user_request_id=user_request_id,
        total_rub=round(total_rub, 2),
        total_usd=round(total_usd, 4),
        total_eur=round(total_eur, 4),
        records_count=len(records)
    )

@app.get("/v1/statistics/summary", response_model=CostsSummaryResponse, tags=["statistics"])
def get_costs_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    group_by: str = Query("day", enum=["day", "week", "month", "service"])
):
    filtered = filter_costs(date_from=date_from, date_to=date_to)
    total_rub = sum(r.rub_amount for r in filtered)
    total_usd = sum(r.usd_amount for r in filtered)
    total_eur = sum(r.eur_amount for r in filtered)
    total_count = len(filtered)

    # Упрощённая группировка (только для демонстрации)
    # В реальном проекте здесь была бы агрегация по БД
    breakdown = []
    if group_by == "service":
        groups = {}
        for r in filtered:
            groups.setdefault(r.service_name, {"rub": 0, "usd": 0, "eur": 0, "count": 0})
            groups[r.service_name]["rub"] += r.rub_amount
            groups[r.service_name]["usd"] += r.usd_amount
            groups[r.service_name]["eur"] += r.eur_amount
            groups[r.service_name]["count"] += 1
        for key, vals in groups.items():
            breakdown.append({
                "group_key": key,
                "rub": round(vals["rub"], 2),
                "usd": round(vals["usd"], 4),
                "eur": round(vals["eur"], 4),
                "records_count": vals["count"]
            })
    else:
        # по дням (упрощённо)
        days = {}
        for r in filtered:
            day = r.created_at.date().isoformat()
            days.setdefault(day, {"rub": 0, "usd": 0, "eur": 0, "count": 0})
            days[day]["rub"] += r.rub_amount
            days[day]["usd"] += r.usd_amount
            days[day]["eur"] += r.eur_amount
            days[day]["count"] += 1
        for key, vals in days.items():
            breakdown.append({
                "group_key": key,
                "rub": round(vals["rub"], 2),
                "usd": round(vals["usd"], 4),
                "eur": round(vals["eur"], 4),
                "records_count": vals["count"]
            })

    return CostsSummaryResponse(
        period={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        total={"rub": round(total_rub, 2), "usd": round(total_usd, 4), "eur": round(total_eur, 4), "records_count": total_count},
        breakdown=breakdown
    )

@app.get("/v1/exchange-rates", response_model=ExchangeRatesResponse, tags=["exchange-rates"])
def get_exchange_rates(limit: int = Query(7, ge=1, le=30)):
    sorted_rates = sorted(exchange_rates_db, key=lambda x: x.date, reverse=True)
    return ExchangeRatesResponse(rates=sorted_rates[:limit])

@app.get("/v1/exchange-rates/{date}", response_model=ExchangeRateResponse, tags=["exchange-rates"])
def get_exchange_rate_by_date(date: date = Path(..., description="Дата в формате YYYY-MM-DD")):
    for rate in exchange_rates_db:
        if rate.date == date:
            return rate
    raise HTTPException(status_code=404, detail=ErrorResponse(
        error="NOT_FOUND",
        message="Курс на указанную дату не найден"
    ).dict())

@app.get("/v1/health/liveness", response_model=HealthResponse, tags=["health"])
def health_liveness():
    return HealthResponse(status="healthy", details={"database": "ok"})

@app.get("/v1/health/readiness", response_model=HealthResponse, tags=["health"])
def health_readiness():
    # Проверяем, что база данных доступна (всегда true для in-memory)
    return HealthResponse(status="healthy", details={"database": "ok"})