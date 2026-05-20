#!/bin/sh
# Запускаем consumer в фоне (Практика №7)
python consumer.py &
# Запускаем API на переднем плане (Практика №3)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
