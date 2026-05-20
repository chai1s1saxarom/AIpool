import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import engine, Base
from app.models import CostRecord, ExchangeRate

# Создание таблиц в базе данных (если они еще не созданы)
Base.metadata.create_all(bind=engine)

# Инициализация сессии
session = Session(bind=engine)

# Заполнение таблицы CostRecord
cost_records = [
    CostRecord(
        id=uuid.uuid4(),
        service_name="AI Text Generation",
        user_request_id=uuid.uuid4(),
        job_id="job-1",
        currency="USD",
        rub_amount=9000.0,
        usd_amount=100.0,
        eur_amount=85.0,
        usd_rate=90.0,
        eur_rate=1.18,
        created_at=datetime.utcnow() - timedelta(days=1)
    ),
    CostRecord(
        id=uuid.uuid4(),
        service_name="Image Recognition",
        user_request_id=uuid.uuid4(),
        job_id="job-2",
        currency="EUR",
        rub_amount=8500.0,
        usd_amount=95.0,
        eur_amount=85.0,
        usd_rate=89.5,
        eur_rate=1.17,
        created_at=datetime.utcnow() - timedelta(days=2)
    )
]

# Заполнение таблицы ExchangeRate
exchange_rates = [
    ExchangeRate(
        id=1,
        date=datetime.utcnow().date() - timedelta(days=1),
        usd_rub=90.0,
        eur_rub=100.0,
        eur_usd=1.18,
        updated_at=datetime.utcnow() - timedelta(days=1)
    ),
    ExchangeRate(
        id=2,
        date=datetime.utcnow().date() - timedelta(days=2),
        usd_rub=89.5,
        eur_rub=99.0,
        eur_usd=1.17,
        updated_at=datetime.utcnow() - timedelta(days=2)
    )
]

# Добавление записей в сессию и сохранение в базе данных
session.add_all(cost_records)
session.add_all(exchange_rates)
session.commit()

# Закрытие сессии
session.close()

print("База данных успешно заполнена тестовыми данными.")
