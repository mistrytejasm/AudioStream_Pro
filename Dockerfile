FROM python:3.12-slim

# Install system dependencies & FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend/app ./app
COPY storage ./storage

# Set Python Path & Environment Variables
ENV PYTHONPATH=/app
ENV ENVIRONMENT=production
ENV PORT=8000

EXPOSE 8000

# Start Uvicorn Server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
