from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum

from app.database import Base

class Currency(str, enum.Enum):
    USD = "USD"
    RUB = "RUB"
    EUR = "EUR"

class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name = Column(String, nullable=False)
    user_request_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    job_id = Column(String, nullable=True)
    currency = Column(String, nullable=False)
    rub_amount = Column(Float, nullable=False)
    usd_amount = Column(Float, nullable=False)
    eur_amount = Column(Float, nullable=False)
    usd_rate = Column(Float, nullable=False)
    eur_rate = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False, index=True)
    usd_rub = Column(Float, nullable=False)
    eur_rub = Column(Float, nullable=False)
    eur_usd = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
