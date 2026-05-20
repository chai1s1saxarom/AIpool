from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas
from datetime import datetime, date
from typing import List, Optional
import uuid
from uuid import UUID

# Функции CRUD для CostRecord
def get_cost_record(db: Session, record_id: UUID):
    return db.query(models.CostRecord).filter(models.CostRecord.id == record_id).first()

def get_cost_records(
        db: Session,
        user_request_id: Optional[UUID] = None,
        service_name: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 20,
        offset: int = 0
):
    query = db.query(models.CostRecord)

    if user_request_id:
        query = query.filter(models.CostRecord.user_request_id == user_request_id)
    if service_name:
        query = query.filter(models.CostRecord.service_name == service_name)
    if date_from:
        dt_from = datetime.combine(date_from, datetime.min.time())
        query = query.filter(models.CostRecord.created_at >= dt_from)
    if date_to:
        dt_to = datetime.combine(date_to, datetime.max.time())
        query = query.filter(models.CostRecord.created_at <= dt_to)

    total = query.count()
    items = query.order_by(models.CostRecord.created_at.desc()).offset(offset).limit(limit).all()

    return {"items": items, "total": total, "limit": limit, "offset": offset}

def create_cost_record(db: Session, record: schemas.CreateCostRecordRequest, converted_amounts):
    db_record = models.CostRecord(
        id=uuid.uuid4(),
        service_name=record.service_name,
        user_request_id=record.user_request_id,
        job_id=record.job_id,
        currency=record.currency,
        rub_amount=converted_amounts["rub"],
        usd_amount=converted_amounts["usd"],
        eur_amount=converted_amounts["eur"],
        usd_rate=converted_amounts["usd_rate"],
        eur_rate=converted_amounts["eur_rate"],
        created_at=datetime.utcnow()
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

def delete_cost_record(db: Session, record_id: UUID):
    db_record = get_cost_record(db, record_id)
    if db_record:
        db.delete(db_record)
        db.commit()
        return True
    return False

# Функции для работы с курсами валют
def get_latest_exchange_rate(db: Session):
    return db.query(models.ExchangeRate).order_by(models.ExchangeRate.date.desc()).first()

def get_exchange_rates(db: Session, limit: int = 7):
    return db.query(models.ExchangeRate).order_by(models.ExchangeRate.date.desc()).limit(limit).all()

def get_exchange_rate_by_date(db: Session, date: date):
    dt = datetime.combine(date, datetime.min.time())
    return db.query(models.ExchangeRate).filter(
        func.date(models.ExchangeRate.date) == date
    ).first()

def create_exchange_rate(db: Session, rate_data):
    db_rate = models.ExchangeRate(**rate_data)
    db.add(db_rate)
    db.commit()
    db.refresh(db_rate)
    return db_rate
