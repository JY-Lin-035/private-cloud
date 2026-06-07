# private-cloud

簡述等待設計中...

## 環境建置

在開始前請先安裝以下工具:

0. Scoop
   - (若要指定位置) \$env:SCOOP='D:\your-path'; [Environment]::SetEnvironmentVariable('SCOOP', $env:SCOOP, 'User')
   - Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   - irm get.scoop.sh | iex
1. nvm
   - scoop install nvm
2. Node.js
   - nvm install lts
   - nvm use lts
3. pnpm
   - npm install -g pnpm
4. uv
   - scoop install uv

### (可選) DataBase (MySQL、Redis)

1. cd db
2. docker-compose up -d

### Backend

1. cd backend
2. uv sync
3. cp .env.example .env
4. 編輯 .env 中 MySQL、Redis、Gmail 相關設定
5. 定義表
   - uv run alembic revision --autogenerate -m "init"
6. 建表
   - uv run alembic upgrade head
7. uv run main.py
8. 啟動寄信佇列
   - uv run celery -A app.tasks.email_tasks worker --loglevel=info (新視窗)

### Frontend

1. cd frontend
2. pnpm install
3. cp .env.example .env
4. 編輯 .env 中 API 基底網址
5. pnpm dev
