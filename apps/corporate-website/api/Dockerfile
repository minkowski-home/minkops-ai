FROM python:3.12-slim

ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY src ./src

USER 10001

CMD ["uvicorn", "minkops_corporate_website_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
