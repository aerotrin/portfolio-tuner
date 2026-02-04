# Minimal frontend Dockerfile for portfolio-tuner
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

COPY src/ ./src/

# Copy legal/disclaimer text for About / Legal page rendering
COPY LEGAL.md /app/LEGAL.md

ENV PYTHONPATH=/app

EXPOSE 8501
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
