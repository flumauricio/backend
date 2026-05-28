# MyApp — FastAPI Backend

> Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Redis · JWT · RBAC

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and POSTGRES_PASSWORD
```

### 2. Start with Docker Compose

```bash
# Backend + Postgres + Redis
docker compose up -d

# Include Adminer DB UI (dev only)
docker compose --profile dev up -d
```

### 3. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 4. Access

| Resource       | URL                               |
|----------------|-----------------------------------|
| API docs       | http://localhost:8000/docs        |
| Healthcheck    | http://localhost:8000/health      |
| Adminer (dev)  | http://localhost:8080             |

---

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── dependencies.py       # Shared FastAPI dependencies
│   │   └── v1/
│   │       ├── router.py         # V1 router aggregator
│   │       └── endpoints/
│   │           ├── auth.py       # Login / register / refresh
│   │           ├── users.py      # User CRUD (RBAC protected)
│   │           └── health.py     # Healthcheck
│   ├── core/
│   │   ├── config.py             # Pydantic Settings
│   │   ├── exceptions.py         # Custom HTTP exceptions
│   │   ├── logging.py            # structlog setup
│   │   ├── rbac.py               # Role-Based Access Control
│   │   └── security.py           # JWT + bcrypt
│   ├── database/
│   │   ├── base.py               # DeclarativeBase + mixins
│   │   ├── session.py            # Async SQLAlchemy engine
│   │   └── redis.py              # Redis async client
│   ├── models/
│   │   └── user.py               # User ORM model
│   ├── schemas/
│   │   ├── user.py               # User Pydantic schemas
│   │   ├── token.py              # JWT schemas
│   │   └── common.py             # Shared response types
│   ├── services/
│   │   ├── user_service.py       # User business logic
│   │   └── auth_service.py       # Auth business logic
│   ├── websocket/
│   │   ├── manager.py            # Connection manager
│   │   └── router.py             # WS endpoint
│   └── main.py                   # App factory + lifespan
├── alembic/                      # DB migrations
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## RBAC Roles

| Role        | Access level                          |
|-------------|---------------------------------------|
| `user`      | Own profile only                      |
| `moderator` | Read any user profile                 |
| `admin`     | Full access (list, update, deactivate)|

---

## Common Commands

```bash
# Generate a new migration
docker compose exec api alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec api alembic upgrade head

# Rollback one step
docker compose exec api alembic downgrade -1

# Logs
docker compose logs -f api
```
