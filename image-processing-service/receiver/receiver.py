import os
import pika

QUEUE = "lab_queue"


def main() -> None:
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    print("Ожидание сообщений", flush=True)
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    def callback(ch, method, _properties, body: bytes) -> None:
        print(f"Получено: {body.decode('utf-8', errors='replace')}", flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE, on_message_callback=callback)
    channel.start_consuming()


if __name__ == "__main__":
    main()
