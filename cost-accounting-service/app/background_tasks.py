import time
import json
from datetime import datetime
import os
from sqlalchemy.orm import Session
from uuid import UUID
from app import models
from app.database import SessionLocal

def log_to_file(message: str):
    """Записывает сообщение в лог-файл"""
    time.sleep(0.5)  # Имитируем задержку операции
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    with open(f"{log_dir}/app.log", "a") as f:
        f.write(f"{timestamp} - {message}\n")


def update_exchange_rates(rates_data: dict):
    """Обновляет курсы валют в базе данных"""
    time.sleep(0.5)  # Имитируем задержку операции

    db = SessionLocal()
    try:
        # Проверяем, есть ли уже запись на эту дату
        date_obj = rates_data.get("date")
        if isinstance(date_obj, str):
            date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()

        existing = db.query(models.ExchangeRate).filter(
            models.ExchangeRate.date == date_obj
        ).first()

        if existing:
            # Обновляем существующую запись
            existing.usd_rub = rates_data.get("usd_rub")
            existing.eur_rub = rates_data.get("eur_rub")
            existing.eur_usd = rates_data.get("eur_usd")
            existing.updated_at = datetime.now()
        else:
            # Создаем новую запись
            new_rate = models.ExchangeRate(
                date=date_obj,
                usd_rub=rates_data.get("usd_rub"),
                eur_rub=rates_data.get("eur_rub"),
                eur_usd=rates_data.get("eur_usd"),
                updated_at=datetime.now()
            )
            db.add(new_rate)

        db.commit()

    except Exception as e:
        db.rollback()
        log_to_file(f"Error updating exchange rates: {str(e)}")
    finally:
        db.close()


def analytics_log(user_request_id: UUID, operation: str, execution_time_ms: int):
    """Логирует аналитические данные для последующего анализа"""
    try:
        data = {
            "timestamp": datetime.now().isoformat(),
            "user_request_id": str(user_request_id),
            "operation": operation,
            "execution_time_ms": execution_time_ms
        }

        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        with open(f"{log_dir}/analytics.log", "a") as f:
            f.write(json.dumps(data) + "\n")
    except Exception as e:
        log_to_file(f"Error logging analytics: {str(e)}")
