# Use official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr for immediate logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADLESS=true

# Set working directory
WORKDIR /app

# Install system dependencies required for curl, certificates, and runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first for optimal Docker layer caching
COPY requirements.txt .

# Install Python packages and Playwright Chromium browser binaries + OS dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Copy project source code
COPY . .

# Ensure runtime directories for data, screenshots, and logs exist
RUN mkdir -p /app/data/screenshots /app/logs

# Execute main scraping pipeline
CMD ["python", "main.py"]
