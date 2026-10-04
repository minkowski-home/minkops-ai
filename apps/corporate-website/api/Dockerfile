FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/corporate-website/api/src:/app/platform/src:/app/connectors/src

WORKDIR /app

COPY apps/corporate-website/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt

COPY apps/corporate-website/api/src /app/apps/corporate-website/api/src
COPY platform/src /app/platform/src
COPY connectors/src /app/connectors/src

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PORT=8080
CMD ["sh", "-c", "uvicorn minkops_corporate_website_api.main:app --host 0.0.0.0 --port ${PORT}"]
