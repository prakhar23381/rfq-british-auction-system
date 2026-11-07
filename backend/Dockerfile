# One image for the API, the Celery worker, Celery Beat and the one-shot migrate/seed job;
# docker-compose.yml picks the command.

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && pip uninstall -y british-auction-backend

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
