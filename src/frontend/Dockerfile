# Minimal frontend Dockerfile for portfolio-tuner
# Build from project root: docker build -f src/frontend/Dockerfile .
FROM python:3.13-slim

WORKDIR /usr/src

COPY src/frontend/pyproject.toml .

RUN pip install --no-cache-dir --upgrade pip && \
pip install --no-cache-dir -e .

COPY src/frontend ./frontend

ENV PYTHONPATH=/usr/src

EXPOSE 8501
CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

