# Используем официальный образ Python 3.11-slim
FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем файл зависимостей (для кэширования слоёв)
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения (при разработке можно не копировать, а использовать bind mount)
COPY main.py .

# Запускаем сервер с авто-перезагрузкой (для разработки)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]