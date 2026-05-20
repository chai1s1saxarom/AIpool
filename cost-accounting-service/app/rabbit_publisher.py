"""
Модуль для публикации событий в RabbitMQ.

"""
import pika
import os
import json
from datetime import datetime

# Имя очереди — одинаковое у publisher и consumer
QUEUE_NAME = "cost_events"


def publish_cost_event(event_type: str, data: dict):
    """
    Публикует событие о затратах в очередь RabbitMQ.

    """
    host = os.getenv("RABBITMQ_HOST", "localhost")

    try:
        # 1. Подключаемся к RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=host)
        )

        # 2. Открываем канал
        channel = connection.channel()

        # 3. Объявляем очередь
        #    durable=True — очередь переживёт перезапуск брокера
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        # 4. Формируем сообщение — оборачиваем данные в конверт с метаданными
        message = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }

        # 5. Публикуем сообщение
        #    delivery_mode=2 — сообщение сохраняется на диск (persistent),
        #    не потеряется при перезапуске RabbitMQ
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(message, default=str).encode('utf-8'),
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )

        # 6. Закрываем соединение
        connection.close()
        print(f"[RabbitMQ] ✓ Событие отправлено: {event_type}")

    except Exception as e:
        # Не бросаем исключение наверх — брокер не должен ломать API
        print(f"[RabbitMQ] ✗ Ошибка публикации: {e}")
