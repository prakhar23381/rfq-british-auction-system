# British Auction RFQ System

A simplified RFQ (Request for Quotation) platform with **British Auction** bidding: suppliers bid openly and keep lowering prices, the auction is extended automatically when there is activity near the close, and it never runs past a hard **forced close** time.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 + Alembic · Celery + Redis · WebSockets · React + TypeScript + Vite

> 🚧 Work in progress.

## Design documents

- [High-level design](docs/HLD.md): architecture, auction rules, key flows, assumptions
- [Database schema](docs/SCHEMA.md): ER diagram, tables, constraints, indexes, DDL
- [API reference](docs/API.md): REST endpoints, error codes, WebSocket events

## Prerequisites

- Python 3.12+
- Node.js 22+
- Docker (with Compose)

## Quick start (local development)

```bash
make setup     # venv, backend + frontend dependencies, backend/.env
make up        # Postgres + Redis in Docker
make migrate   # create the tables
make seed      # demo users and auctions (make seed args=--reset to start over)
```

Then, in separate terminals:

```bash
make api       # FastAPI on http://localhost:8000  (Swagger UI: /docs)
make worker    # Celery worker: opens and closes auctions at their exact times
make beat      # Celery Beat: runs a sweep every 5 s as a safety net for missed jobs
make web       # React app on http://localhost:5173
```

Run `make help` to list all commands.

## Checks

```bash
make check     # ruff + oxlint, mypy + tsc, pytest, frontend build
```

## Repository layout

```
backend/    FastAPI app, SQLAlchemy models, Alembic migrations, Celery tasks, tests
frontend/   React + TypeScript SPA (Vite)
docs/       HLD, schema design, API reference
infra/      Docker init scripts
```
