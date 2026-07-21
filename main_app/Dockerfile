# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install system dependencies
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

# Set the working directory in the container
WORKDIR /app

# Copy the wheel files and requirements.txt into the container
COPY requirements.txt /app/

# Install Python dependencies from wheels first, then from requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.python.org -r /app/requirements.txt

# Copy the rest of the application code
COPY . /app

# Make port 1024 available to the world outside this container
EXPOSE 1024

# Run your application
CMD ["python", "app.py"]
