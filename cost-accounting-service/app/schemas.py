from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict
from datetime import date, datetime
from enum import Enum

class Currency(str, Enum):
    USD = "USD"
    RUB = "RUB"
    EUR = "EUR"

# Базовые модели для запросов
class CreateCostRecordRequest(BaseModel):
    service_name: str
    user_request_id: UUID4
    job_id: Optional[str] = None
    currency: Currency
    amount: float = Field(gt=0)

class CreateCostRecordV2Request(BaseModel):
    service_name: str
    user_request_id: UUID4
    job_id: Optional[str] = None
    model_id: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)

# Модели ответов
class CostRecordResponse(BaseModel):
    id: UUID4
    service_name: str
    user_request_id: UUID4
    job_id: Optional[str]
    currency: Currency
    rub_amount: float
    usd_amount: float
    eur_amount: float
    usd_rate: float
    eur_rate: float
    created_at: datetime

    class Config:
        from_attributes = True

class CostRecordListResponse(BaseModel):
    items: List[CostRecordResponse]
    total: int
    limit: int
    offset: int

class UserRequestCostResponse(BaseModel):
    user_request_id: UUID4
    total_rub: float
    total_usd: float
    total_eur: float
    records_count: int

class CostsSummaryResponse(BaseModel):
    period: Dict
    total: Dict
    breakdown: List[Dict]

class ExchangeRateResponse(BaseModel):
    date: date
    usd_rub: float
    eur_rub: float
    eur_usd: Optional[float] = None
    updated_at: datetime

    class Config:
        from_attributes = True

class ExchangeRatesResponse(BaseModel):
    rates: List[ExchangeRateResponse]

class HealthResponse(BaseModel):
    status: str
    details: Optional[Dict] = None

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Dict] = None
