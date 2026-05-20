"""
Утилиты для работы с RabbitMQ (Практика №7).
Producer публикует задачи в очередь llm_jobs.
"""
import pika
import json
import os

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "llm_jobs"


def get_connection() -> pika.BlockingConnection:
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            connection_attempts=5,
            retry_delay=2,
        )
    )


def publish_job(job_id: str, payload: dict) -> None:
    """
    Отправить задачу в очередь RabbitMQ.
    Вызывается как BackgroundTask после сохранения задачи в БД.
    """
    try:
        connection = get_connection()
        channel = connection.channel()
        # durable=True — очередь переживёт перезапуск RabbitMQ
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            # delivery_mode=2 — сообщение сохраняется на диск
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
        print(f"[RabbitMQ] ✓ Опубликована задача job_id={job_id}")
    except Exception as e:
        print(f"[RabbitMQ] ✗ Ошибка публикации job_id={job_id}: {e}")


def check_rabbitmq() -> bool:
    """Проверить доступность RabbitMQ (используется в /health/readiness)."""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False
