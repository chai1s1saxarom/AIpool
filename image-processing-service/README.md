# Image Processing Service

Сервис асинхронной генерации и управления изображениями (FastAPI + async SQLAlchemy + PostgreSQL).

## Запуск

### Полный стек (рекомендуется)

Из корня репозитория:

```bash
docker compose up --build -d
```

Сервис доступен внутри сети Docker как `http://image-service:8000`. UI — через Gateway: http://localhost:8080

### Локально (только image + БД)

```bash
docker compose up -d db rabbitmq
export DATABASE_URL=postgresql+asyncpg://postgres:123@localhost:5432/image_db
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5673/` | Брокер для `/v1/rabbit/messages` |
| `SKIP_JOB_PROCESSING` | — | `1` — не запускать фоновую генерацию (для тестов) |

## Эндпоинты

```
POST /v1/images/jobs          — создать задачу (202)
GET  /v1/images/jobs/{id}     — статус задачи
GET  /v1/images               — список изображений
GET  /v1/providers            — провайдеры (dalle-3, kandinsky, yandexart)
GET  /v1/health/liveness
GET  /v1/health/readiness
```

## Провайдеры

- `dalle-3` — DALL-E 3
- `kandinsky` — Kandinsky 3.0
- `yandexart` — YandexART

## Тесты

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Тесты используют SQLite in-memory (`SKIP_JOB_PROCESSING=1`).

## Структура

```
image-processing-service/
├── app/
├── alembic/
├── receiver/           # RabbitMQ receiver
├── tests/
└── Dockerfile
```
