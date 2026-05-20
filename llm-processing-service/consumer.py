"""
RabbitMQ Consumer (Практика №7).
Слушает очередь llm_jobs и симулирует обработку LLM-запроса.
Запускается как отдельный процесс через start.sh.
"""
import pika
import json
import os
import time
from datetime import datetime, timezone

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "llm_jobs"


def process_job(job_id: str, model_id: str, messages: list) -> dict:
    """
    Симулятор LLM-обработки.
    В реальном проекте здесь был бы вызов OpenAI/Gemini SDK.
    """
    time.sleep(1.5)  # имитация обращения к LLM API

    input_text = " ".join(m.get("content", "") for m in messages)
    input_tokens = max(1, len(input_text) // 4)
    output_tokens = 150

    response_text = (
        f"[Симуляция {model_id}] Обработано {input_tokens} токенов. "
        f"Ответ на: «{input_text[:60]}{'...' if len(input_text) > 60 else ''}»"
    )

    return {
        "response": response_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def update_job_in_db(job_id: str, result: dict, processing_time_ms: int):
    """Обновляет статус задачи в PostgreSQL после обработки."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        job = db.get(models.LLMJob, job_id)
        if not job:
            print(f"[Consumer] Задача {job_id} не найдена в БД")
            return

        job.status = "done"
        job.result_response = result["response"]
        job.result_input_tokens = result["input_tokens"]
        job.result_output_tokens = result["output_tokens"]
        job.result_total_cost_usd = round(
            result["input_tokens"] * 0.00000015 +
            result["output_tokens"] * 0.0000006, 6
        )
        job.processing_time_ms = processing_time_ms
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        print(f"[Consumer] ✓ Задача {job_id} завершена за {processing_time_ms} мс")
    except Exception as e:
        db.rollback()
        print(f"[Consumer] ✗ Ошибка обновления {job_id}: {e}")
    finally:
        db.close()


def callback(ch, method, properties, body):
    """
    Обработчик входящего сообщения.
    Вызывается автоматически при поступлении задачи в очередь.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
        job_id = payload.get("job_id", "unknown")
        model_id = payload.get("llm_model_id", "unknown")
        messages = payload.get("messages", [])

        print(f"\n[Consumer] Получена задача: job_id={job_id}, model={model_id}")

        start = int(time.time() * 1000)
        result = process_job(job_id, model_id, messages)
        processing_time = int(time.time() * 1000) - start

        update_job_in_db(job_id, result, processing_time)

        # ACK — подтверждаем что сообщение обработано (RabbitMQ удалит его из очереди)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[Consumer] ✗ Ошибка: {e}")
        # NACK — сообщение не обработано, не возвращать в очередь
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    print("[Consumer] Запуск потребителя RabbitMQ...")
    print(f"[Consumer] Хост: {RABBITMQ_HOST}, очередь: {QUEUE_NAME}")
    print("[Consumer] Ожидание задач (Ctrl+C для выхода)")

    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    connection_attempts=5,
                    retry_delay=3,
                )
            )
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            # prefetch_count=1 — брать по одной задаче за раз
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback,
                auto_ack=False,  # подтверждаем вручную через basic_ack
            )
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            print("[Consumer] Нет соединения с RabbitMQ. Повтор через 5 сек...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[Consumer] Остановлен")
            break
        except Exception as e:
            print(f"[Consumer] Ошибка: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
