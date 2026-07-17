<div align="center">
  <img src="frontend/src/assets/meow-cloud-mark.png" alt="Meow Cloud" width="140" />
  <h1>Meow Cloud</h1>
  <p>A self-hosted personal cloud storage service for managing files, permissions, and storage under your own control.</p>
  <p>
    <a href="README.md">繁體中文</a>
  </p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.136%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=20232A" alt="React 19" />
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white" alt="MySQL 8" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis 7" />
</p>

## Highlights

Meow Cloud is a self-hosted personal cloud storage service focused on data ownership. It brings account verification, file and folder management, share links, and storage administration into one interface. The backend uses FastAPI for APIs and access control, the frontend uses React for the user interface, and MySQL, Redis, and Celery support persistence, sessions, and background jobs.

## Defaults

Default limits are `500 MiB` per file, `10 GiB` per user, a `30-minute` session, and a `30-second` download token. Per-user total storage can be changed by an administrator.

Registration passwords must be 12 to 100 characters long and include uppercase letters, lowercase letters, digits, and three different symbols.

## Technology Stack

| Area | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, Axios, Zustand, Ant Design, Tailwind CSS |
| Upload and charts | Uppy, ApexCharts, Recharts, Lucide React |
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Database and cache | MySQL 8, Redis 7 |
| Background jobs | Celery |
| Migrations | Alembic |
| Password hashing | Argon2id |

## Architecture

```text
┌──────────────────────────────┐
│ React + TypeScript + Vite    │
└──────────────┬───────────────┘
               │ HTTP API / Cookie Session
               ▼
┌──────────────────────────────┐
│ FastAPI + SQLAlchemy         │
│ Account / File / Folder /    │
│ Share / Admin Services       │
└───────┬──────────────┬───────┘
        │              │
        ▼              ▼
   ┌─────────┐    ┌─────────┐
   │ MySQL   │    │ Redis   │
   └─────────┘    └────┬────┘
                       ▼
                 Celery Worker ── SMTP
```

- `frontend`: React UI, routing, file operations, and storage display.
- `backend`: FastAPI APIs, authentication, file and folder services, sharing, and administration.
- `db`: Docker Compose configuration for MySQL 8 and Redis 7.
- File contents are stored in `backend/storage/app/private/files` by default; MySQL stores indexes and metadata.

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/v1/       # API routers
│   │   ├── models/       # SQLAlchemy models
│   │   ├── repositories/ # Data access layer
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── tasks/        # Celery tasks
│   │   └── utils/        # Security and utility functions
│   ├── alembic/          # Database migrations
│   ├── storage/          # Private file storage
│   ├── tests/            # Backend tests
│   ├── main.py
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/          # API clients
│   │   ├── components/   # Shared components
│   │   ├── pages/        # Application pages
│   │   └── router/       # Client-side routes
│   ├── package.json
│   └── .env.example
├── db/
│   └── docker-compose.yaml
├── README.md             # Traditional Chinese
└── README.en.md          # English
```

## Quick Start

### Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- Node.js LTS
- [pnpm](https://pnpm.io/)
- Docker Desktop or a compatible Docker Compose environment
- An SMTP provider for email verification and password-reset workflows

### 1. Start the infrastructure

```bash
docker compose -f db/docker-compose.yaml up -d
```

The default services are MySQL at `127.0.0.1:3306` and Redis at `127.0.0.1:6379`.

Redis database `0` is the default logical Redis database. It is different from the Redis port `6379`.

### 2. Configure and start the backend

```bash
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run main.py
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`. Review the database, Redis, SMTP, and storage settings in `backend/.env`.

The backend listens on `http://127.0.0.1:8000` by default.

### 3. Start the background task service

```bash
cd backend
uv run celery -A app.tasks.email_tasks worker --loglevel=info
```

To enable scheduled cleanup and storage recalculation:

```bash
cd backend
uv run celery -A app.tasks.cleanup_tasks worker --beat --loglevel=info
```

### 4. Configure and start the frontend

```bash
cd frontend
pnpm install
cp .env.example .env
pnpm dev
```

Set the API base URL in `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

## Environment Variables

Backend settings are stored in `backend/.env`; use `backend/.env.example` as a starting point.

| Variable | Purpose |
| --- | --- |
| `APP_URL` | Application URL used by the backend and email verification links |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | MySQL connection settings |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | Redis connection settings |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | SMTP settings |
| `STORAGE_BASE_PATH` | Private file storage path |
| `TOKEN_EXPIRE_TIME` | Session lifetime in minutes |
| `DOWNLOAD_TOKEN_EXPIRE_SECONDS` | File download token lifetime |

Frontend settings are stored in `frontend/.env`:

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | FastAPI API base URL |

## API Documentation

Once the backend is running:

- Swagger UI: [`/docs`](http://127.0.0.1:8000/docs)
- ReDoc: [`/redoc`](http://127.0.0.1:8000/redoc)
- Health check: [`/health`](http://127.0.0.1:8000/health)

| Prefix | Purpose |
| --- | --- |
| `/api/accounts` | Registration, login, email and password operations, sessions, and administration |
| `/api/files` | File listing, upload, download, deletion, restoration, and storage information |
| `/api/folders` | Folder creation, renaming, deletion, restoration, and paths |
| `/api/share` | Share link creation, listing, deletion, and public downloads |
| `/api/email/verify` | Email verification links |

## Development Commands

```bash
cd backend
uv run pytest tests/ -v

cd frontend
pnpm lint
pnpm build
pnpm preview
```

## Deployment Notes

- Replace the development CORS setting with explicit frontend origins in production.
- Session cookies use `Secure` and `SameSite=None`; cross-origin deployments require HTTPS.
- Do not expose `backend/storage/app/private/files` as a public static directory.
- Replace the default MySQL and Redis passwords before production deployment.
- Use a dedicated SMTP credential and keep production secrets out of version control.
- Plan for file-storage backups, a reverse proxy, HTTPS certificates, log retention, and Celery worker monitoring.
