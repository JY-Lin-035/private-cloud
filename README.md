<div align="center">
  <img src="frontend/src/assets/meow-cloud-mark.png" alt="Meow Cloud" width="140" />
  <h1>Meow Cloud</h1>
  <p>自架式個人雲端儲存服務，讓檔案、權限與儲存環境由自己管理。</p>
  <p>
    <a href="README.en.md">English</a>
  </p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.136%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=20232A" alt="React 19" />
  <img src="https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white" alt="MySQL 8" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis 7" />
</p>

## 特色

Meow Cloud 是一個以自架與資料自主為核心的個人雲端儲存服務，將帳戶驗證、檔案與資料夾管理、分享連結及儲存空間管理整合在同一個介面。後端採用 FastAPI 處理 API 與權限，前端以 React 提供操作介面，並使用 MySQL、Redis 與 Celery 支援資料、Session 與背景任務。

## 預設設定

預設限制：單一檔案 `500 MiB`、每位使用者 `10 GiB`、Session `30 分鐘`、下載 Token `30 秒`。容量限制可由管理員調整。

註冊密碼須為 12 至 100 個字元，且至少包含大寫字母、小寫字母、數字與三種不同符號。

## 技術堆疊

| 區域 | 技術 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、React Router、Axios、Zustand、Ant Design、Tailwind CSS |
| 上傳與視覺化 | Uppy、ApexCharts、Recharts、Lucide React |
| 後端 | Python 3.12+、FastAPI、SQLAlchemy、Pydantic |
| 資料庫與快取 | MySQL 8、Redis 7 |
| 背景任務 | Celery |
| 資料庫遷移 | Alembic |
| 密碼雜湊 | Argon2id |

## 系統架構

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

- `frontend`：使用者介面、路由、檔案操作與儲存空間顯示。
- `backend`：FastAPI API、驗證、檔案服務、資料夾服務、分享服務與管理員 API。
- `db`：Docker Compose 設定，負責啟動 MySQL 8 與 Redis 7。
- 檔案內容預設儲存在 `backend/storage/app/private/files`；MySQL 儲存檔案索引與 metadata。

## 專案結構

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
├── README.md             # 繁體中文
└── README.en.md          # English
```

## 快速開始

### 環境需求

- Python 3.12 或以上
- [uv](https://docs.astral.sh/uv/)
- Node.js LTS
- [pnpm](https://pnpm.io/)
- Docker Desktop 或相容的 Docker Compose 環境
- SMTP 服務；若要啟用信箱驗證與密碼重設，必須設定 SMTP

### 1. 啟動基礎服務

```bash
docker compose -f db/docker-compose.yaml up -d
```

預設連線資訊：

| 服務 | 位址 | 設定 |
| --- | --- | --- |
| MySQL | `127.0.0.1:3306` | Database `my_database`、User `mysql`、Password `mysql` |
| Redis | `127.0.0.1:6379` | Database `0` |

Redis 的 `0` 是邏輯資料庫編號，代表使用 Redis 預設的第 0 個資料庫，與 Redis 的 `6379` 連接埠不同。

### 2. 設定並啟動後端

```bash
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run main.py
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

請在 `backend/.env` 確認資料庫、Redis、SMTP 與儲存路徑設定。後端預設執行於 `http://127.0.0.1:8000`。

### 3. 啟動背景任務服務

寄送驗證信與驗證碼需要另外啟動 Celery 背景任務服務：

```bash
cd backend
uv run celery -A app.tasks.email_tasks worker --loglevel=info
```

若要啟用定期清理與儲存空間重新計算：

```bash
cd backend
uv run celery -A app.tasks.cleanup_tasks worker --beat --loglevel=info
```

### 4. 設定並啟動前端

```bash
cd frontend
pnpm install
cp .env.example .env
pnpm dev
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

`frontend/.env`：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

## 環境變數

後端設定位於 `backend/.env`，範例檔案為 `backend/.env.example`。

| 變數 | 用途 |
| --- | --- |
| `APP_URL` | 後端與信箱驗證連結使用的應用程式網址 |
| `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` | MySQL 連線設定 |
| `REDIS_HOST`、`REDIS_PORT`、`REDIS_DB` | Redis 連線設定 |
| `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM` | SMTP 寄信設定 |
| `STORAGE_BASE_PATH` | 私有檔案儲存路徑 |
| `TOKEN_EXPIRE_TIME` | Session 有效時間，單位為分鐘 |
| `DOWNLOAD_TOKEN_EXPIRE_SECONDS` | 檔案下載 Token 有效時間 |

前端設定位於 `frontend/.env`：

| 變數 | 用途 |
| --- | --- |
| `VITE_API_BASE_URL` | FastAPI API 基底網址 |

## API 文件

後端啟動後可使用 FastAPI 自動產生的文件：

- Swagger UI：[`/docs`](http://127.0.0.1:8000/docs)
- ReDoc：[`/redoc`](http://127.0.0.1:8000/redoc)
- Health check：[`/health`](http://127.0.0.1:8000/health)

主要路由：

| 路由前綴 | 用途 |
| --- | --- |
| `/api/accounts` | 註冊、登入、信箱與密碼、Session、管理員功能 |
| `/api/files` | 檔案列表、上傳、下載、刪除、還原與儲存空間 |
| `/api/folders` | 資料夾建立、重新命名、刪除、還原與路徑 |
| `/api/share` | 分享連結建立、查詢、刪除與公開下載 |
| `/api/email/verify` | 電子信箱驗證連結 |

## 常用指令

```bash
# Backend tests
cd backend
uv run pytest tests/ -v

# Frontend checks
cd frontend
pnpm lint
pnpm build
pnpm preview
```

## 部署注意事項

- 正式環境請將 CORS origins 改為明確的前端網域。
- Session Cookie 使用 `Secure` 與 `SameSite=None`，跨來源部署必須使用 HTTPS。
- 不要將 `backend/storage/app/private/files` 暴露為公開靜態目錄。
- MySQL 與 Redis 的預設密碼僅適用於本機開發，正式環境必須更換。
- SMTP 請使用應用程式密碼或專用憑證，並避免將秘密提交至版本控制。
- 正式環境應另行規劃檔案備份、反向代理、HTTPS 憑證、日誌保存與 Celery worker 監控。