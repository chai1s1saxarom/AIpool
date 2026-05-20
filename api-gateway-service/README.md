# API Gateway Service

Единая точка входа (BFF) для связи UI с микросервисами LLM, Image и Cost Accounting. Реализует спецификацию `openapi/api-router-service.yaml`.

## Возможности

- Управление чатами и историей сообщений (SQLite)
- Маршрутизация запросов: `llm` → LLM Processing, `image` → Image Processing
- Фоновый polling статуса задач и запись затрат в Cost Accounting
- Веб-интерфейс на `/` (статические файлы в `static/`)

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LLM_SERVICE_URL` | `http://localhost:8001` | URL LLM-сервиса |
| `IMAGE_SERVICE_URL` | `http://localhost:8002` | URL Image-сервиса |
| `COST_SERVICE_URL` | `http://localhost:8003` | URL Cost-сервиса |
| `DATABASE_URL` | `sqlite:///./gateway.db` | БД чатов |

## Локальный запуск

```bash
pip install -r requirements.txt
export LLM_SERVICE_URL=http://localhost:8001
export IMAGE_SERVICE_URL=http://localhost:8002
export COST_SERVICE_URL=http://localhost:8003
uvicorn app.main:app --reload --port 8080
```

Рекомендуется поднимать весь стек: `docker compose up` из корня репозитория.

## Основные эндпоинты

```
GET  /                          — веб-интерфейс
GET  /v1/chats                  — список чатов
POST /v1/chats                  — создать чат
POST /v1/messages/send          — отправить сообщение (llm | image)
GET  /v1/messages/{id}/status   — статус обработки
GET  /v1/services/status        — доступность backend-сервисов
GET  /v1/health/liveness
GET  /v1/health/readiness
```

## Тесты

```bash
pytest tests/ -v
```
