# Minimal backend Dockerfile for portfolio-tuner
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

COPY src/ ./src/

# SQLite parent dir must exist
RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
