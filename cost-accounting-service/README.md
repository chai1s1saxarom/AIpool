# Cost Accounting Service

Микросервис учёта затрат на использование AI-сервисов с конвертацией валют и публикацией событий в RabbitMQ.

## Запуск

```bash
docker compose up --build
```

| Компонент | Порт |
|-----------|------|
| API | http://localhost:8003 |
| Swagger | http://localhost:8003/docs |
| PostgreSQL | 5434 |
| RabbitMQ UI | http://localhost:15672 |

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | PostgreSQL connection string |
| `RABBITMQ_HOST` | Хост брокера (в Docker: `rabbitmq`) |
| `EXCHANGE_RATE_API_KEY` | Ключ внешнего API курсов (опционально) |

## Эндпоинты

```
GET  /v1/costs                    — список записей
POST /v1/costs                    — создать запись (ручная сумма)
POST /v2/costs                    — создать по токенам модели
GET  /v1/costs/{cost_id}
DELETE /v1/costs/{cost_id}
GET  /v1/exchange-rates
GET  /v1/health/liveness
GET  /v1/health/readiness
```

## Интеграция

API Gateway записывает затраты после завершения LLM/Image задач:

- LLM → `POST /v2/costs` (токены + model_id)
- Image → `POST /v1/costs` (сумма в USD)

## Структура

```
cost-accounting-service/
├── main.py
├── app/
├── consumer/          # RabbitMQ consumer cost_events
├── alembic/
└── docker-compose.yml
```
