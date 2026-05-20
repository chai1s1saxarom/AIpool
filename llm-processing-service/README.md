# LLM Processing Service

Микросервис асинхронной обработки запросов к LLM-провайдерам.

## Покрытие практических работ

| Практика | Что реализовано |
|----------|----------------|
| №3 | Dockerfile, bind mount, live-reload |
| №4 | docker-compose.yml, сети, depends_on, healthcheck |
| №5 | PostgreSQL + SQLAlchemy + Pydantic модели + CRUD |
| №6 | `async def`, `BackgroundTasks` (лог + публикация в RabbitMQ) |
| №7 | RabbitMQ producer в API, consumer в `consumer.py` |

## Структура

```
llm-processing-service/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── start.sh           # запускает API + consumer
├── consumer.py        # RabbitMQ consumer (Практика №7)
└── app/
    ├── main.py        # все эндпоинты
    ├── database.py    # подключение к PostgreSQL
    ├── models.py      # SQLAlchemy модель LLMJob
    ├── schemas.py     # Pydantic схемы
    ├── rabbit.py      # утилиты RabbitMQ
    └── models_registry.py  # реестр LLM-моделей
```

## Запуск

```bash
docker-compose up --build
```

## Доступ

| Что | Адрес |
|-----|-------|
| Swagger UI | http://localhost:8000/docs |
| RabbitMQ UI | http://localhost:15672 (guest/guest) |

## Эндпоинты

```
GET  /v1/health/liveness            — сервис живой
GET  /v1/health/readiness           — проверка БД + RabbitMQ
GET  /v1/models                     — список LLM-моделей
GET  /v1/models/{model_id}          — детали модели
GET  /v1/llm/jobs                   — список задач
POST /v1/llm/jobs                   — создать задачу → RabbitMQ
GET  /v1/llm/jobs/{job_id}          — статус задачи
DELETE /v1/llm/jobs/{job_id}        — отменить задачу
GET  /v1/llm/trace/{user_request_id} — трейс запроса
```

## Поддерживаемые модели

- `openai_gpt-4o-mini`
- `openai_gpt-4o`
- `google_gemini-1.5-flash`
- `google_gemini-1.5-pro`
- `anthropic_claude-3-haiku`

## Как работает флоу

```
POST /v1/llm/jobs
  → сохранить в PostgreSQL (статус: pending)
  → [фон] опубликовать в RabbitMQ
  → [фон] записать лог
  → вернуть job_id клиенту (202 Accepted)

consumer.py слушает очередь llm_jobs
  → получить задачу
  → симулировать LLM-ответ
  → обновить статус в PostgreSQL (done)
  → ACK сообщение

GET /v1/llm/jobs/{job_id}  ← клиент polling'ом проверяет статус
```
