FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir pika

COPY receiver.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "receiver.py"]
