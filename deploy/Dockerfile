# Single-container image for platforms that run one service (Render free plan):
# the API serves the built React app and runs the Celery worker + Beat beside it.
# Build from the repository root: docker build -f deploy/Dockerfile .
# (docker-compose.yml uses backend/Dockerfile and frontend/Dockerfile instead.)

FROM node:22-alpine AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && pip uninstall -y british-auction-backend

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static
RUN useradd --create-home --uid 10001 app
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=web /src/dist ./static
# Precompile, so a cold start on a slow CPU doesn't compile the app's modules every time.
RUN python -m compileall -q /app/app /app/scripts /app/alembic
USER app
EXPOSE 8000
CMD ["bash", "scripts/start_single.sh"]
