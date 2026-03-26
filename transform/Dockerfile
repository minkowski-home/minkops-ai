FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files (dbt_packages excluded via .dockerignore — installed below)
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DBT_PROFILES_DIR=/app

# Resolve and install dbt package dependencies at image build time so the
# runtime container has no network dependency and packages are baked in.
RUN dbt deps

# Seed reference data first (agent_type_labels, ticket_priority_sla), then
# run models. Seeds must exist before gold models that ref() them can build.
CMD ["sh", "-c", "dbt seed && dbt run"]