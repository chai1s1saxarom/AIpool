"""
Cost Consumer — получатель событий из очереди RabbitMQ.

Слушает очередь cost_events
"""
import pika
import os
import json
import time

QUEUE_NAME = "cost_events"


def process_event(event_type: str, data: dict, timestamp: str):
    """
    Бизнес-логика обработки события.
    """
    print(f"\n{'=' * 55}")
    print(f"  Новое событие : {event_type}")
    print(f"  Время         : {timestamp}")
    print(f"  Сервис        : {data.get('service_name', '—')}")
    print(f"  request_id    : {data.get('user_request_id', '—')}")
    print(f"  Сумма USD     : {data.get('usd_amount', '—')}")
    print(f"  Сумма RUB     : {data.get('rub_amount', '—')}")
    print(f"  Сумма EUR     : {data.get('eur_amount', '—')}")

    if event_type == "cost_record_created_v2":
        print(f"  Модель        : {data.get('model_id', '—')}")
        print(f"  Токены (вх.)  : {data.get('prompt_tokens', '—')}")
        print(f"  Токены (вых.) : {data.get('completion_tokens', '—')}")

    print(f"{'=' * 55}")


def callback(ch, method, properties, body):
    """
    Функция-обработчик: вызывается автоматически при получении сообщения.
    """
    try:

        message = json.loads(body.decode('utf-8'))

        event_type = message.get("event_type", "unknown")
        timestamp  = message.get("timestamp", "")
        data       = message.get("data", {})

        process_event(event_type, data, timestamp)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[Consumer] Ошибка обработки: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main():
    host = os.getenv("RABBITMQ_HOST", "localhost")

    print("=" * 55)
    print("  Cost Accounting Consumer")
    print(f"  RabbitMQ host : {host}")
    print(f"  Очередь       : {QUEUE_NAME}")
    print("  Ожидание событий... (Ctrl+C для выхода)")
    print("=" * 55)

    while True:
        try:
            # 1. Подключаемся
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=host)
            )
            channel = connection.channel()

            # 2. Объявляем очередь
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            # 3. берём по одному сообщению,
            channel.basic_qos(prefetch_count=1)

            # 4. Подписываемся
            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback,
                auto_ack=False
            )

            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError:
            print("[Consumer] Нет соединения с RabbitMQ. Повтор через 5 сек...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[Consumer] Остановлен вручную.")
            break
        except Exception as e:
            print(f"[Consumer] Неожиданная ошибка: {e}. Повтор через 5 сек...")
            time.sleep(5)


if __name__ == "__main__":
    main()
