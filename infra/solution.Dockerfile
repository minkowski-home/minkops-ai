FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/minkops/.venv/bin:$PATH
WORKDIR /opt/minkops
COPY pyproject.toml uv.lock ./
COPY platform ./platform
COPY connectors ./connectors
COPY db ./db
COPY employees ./employees
COPY solutions ./solutions
COPY apps/solution-api ./apps/solution-api
COPY apps/corporate-website/api ./apps/corporate-website/api
# Editable workspace packages retain repository-relative employee/client bundles.
# The image is immutable; production never loads definitions from a workstation.
RUN uv sync --frozen --no-dev --package minkops-solution-api \
    && useradd --create-home --uid 10001 minkops
USER minkops
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn minkops_api.main:app --host 0.0.0.0 --port ${PORT}"]
