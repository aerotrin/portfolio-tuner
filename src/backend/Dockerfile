# Minimal backend Dockerfile for portfolio-tuner
# Build from project root: docker build -f src/backend/Dockerfile .
FROM python:3.13-slim

WORKDIR /usr/src

COPY src/backend/pyproject.toml .

RUN pip install --no-cache-dir --upgrade pip && \
pip install --no-cache-dir -e .

COPY src/backend ./backend

ENV PYTHONPATH=/usr/src

EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
