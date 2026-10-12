FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY apps/api/app ./app
RUN useradd --create-home api
# The app_data volume mounts here; both api and worker (non-root) write under it.
RUN mkdir -p /data/storage && chown -R api:api /data
USER api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS checks
USER root
COPY apps/api/requirements-dev.lock ./requirements-dev.lock
RUN pip install --no-cache-dir -r requirements-dev.lock
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY apps/api/tests ./tests
RUN chown -R api:api /app
USER api
CMD ["sh", "-c", "ruff check . && ruff format --check . && mypy && pytest"]

FROM base AS runtime
