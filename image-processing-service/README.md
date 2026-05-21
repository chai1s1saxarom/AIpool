# Image Processing Service

Сервис асинхронной генерации и управления изображениями (FastAPI + async SQLAlchemy + PostgreSQL).

## Запуск

### Полный стек (БД, API, Prometheus, Grafana, RabbitMQ)

```bash
cd image-processing-service
cp .env.example .env   # при необходимости
docker compose up --build -d
```

| Сервис | URL |
|--------|-----|
| API + Swagger | http://localhost:8000/docs |
| Prometheus targets | http://localhost:9090/targets |
| Grafana | http://localhost:3000 (логин `admin` / `admin`) |
| RabbitMQ UI | http://localhost:15673 |

Дашборд **Image Processing Service** (RPS, latency p95, error rate) подключается автоматически из `grafana/dashboards/`.

### Локально (только API + БД)

```bash
docker compose up -d db rabbitmq
export DATABASE_URL=postgresql+asyncpg://postgres:123@localhost:5432/image_db
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Для Prometheus укажите target `host.docker.internal:8000` в `prometheus/prometheus.yml`, если API запущен на хосте.

## Observability (лабораторная)

### Чек-лист для сдачи

- [ ] `GET /metrics` — метрики в формате Prometheus
- [ ] http://localhost:9090/targets — job `image-processing-service`, статус **UP**
- [ ] Grafana — три графика: **RPS**, **latency p95**, **error rate**
- [ ] Логи в stdout — **JSON**, поле `correlation_id`
- [ ] Заголовок ответа **X-Request-ID** (дополнительно)
- [ ] Тестовые запросы: нормальные, ошибочные (404), медленные

### Тестовый трафик

```bash
pip install httpx
python scripts/verify_observability.py --base-url http://localhost:8000
```

Примеры запросов:

```bash
# нормальный
curl -H "X-Request-ID: my-test-id" http://localhost:8000/v1/health/liveness

# ошибка 404
curl http://localhost:8000/v1/images/00000000-0000-0000-0000-000000000099

# медленный (~2 с)
curl "http://localhost:8000/v1/debug/slow?delay=2"

# метрики
curl http://localhost:8000/metrics
```

### Переменные

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5673/` | Брокер |
| `SKIP_JOB_PROCESSING` | — | `1` — без фоновой генерации (тесты) |
| `ENABLE_METRICS` | `true` | `false` — отключить `/metrics` |

## CI/CD (GitHub Actions)

Workflow: `.github/workflows/ci-cd.yml` (в корне репозитория AIpool).

При push в `main` / `master`:

1. `pytest` в `image-processing-service`
2. Сборка и push образа:
   - `ghcr.io/<ваш-логин>/image-processing-service:<sha>`
   - `ghcr.io/<ваш-логин>/image-processing-service:latest`
3. Job `deploy` — заглушка `echo Deploy`
4. (опционально) Telegram — секреты `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

Для PR без публикации образа: `.github/workflows/image-processing-pr.yml`.

**Публикация в ghcr.io:** в настройках репозитория включите *Packages → Inherit access* или сделайте пакет public после первого push.

## Эндпоинты

```
GET  /metrics                 — Prometheus
POST /v1/images/jobs          — создать задачу (202)
GET  /v1/images/jobs/{id}
PUT  /v1/images/jobs/{id}
GET  /v1/external/posts/{id}  — JSONPlaceholder
GET  /v1/external/aggregate   — параллельные запросы
POST /v1/rabbit/messages        — очередь lab_queue
GET  /v1/logs                   — журнал действий в БД
GET  /v1/debug/slow             — медленный запрос для Grafana
```

## Тесты

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Структура

```
image-processing-service/
├── app/
│   ├── logging_config.py   # JSON-логи + correlation_id
│   ├── middleware.py       # X-Request-ID
│   └── metrics.py          # /metrics
├── prometheus/
├── grafana/
├── receiver/
├── scripts/verify_observability.py
└── tests/
```
