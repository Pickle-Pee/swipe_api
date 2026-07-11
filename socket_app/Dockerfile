# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libpq-dev \
    libmagic1 \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только необходимые файлы
COPY requirements.txt /app/

# Устанавливаем зависимости
RUN pip install --no-cache-dir --trusted-host pypi.python.org -r /app/requirements.txt

# **Не копируем исходный код, так как он будет монтироваться через volumes**

# Открываем порт
EXPOSE 1025

# Устанавливаем команду запуска
CMD ["python", "app.py"]
