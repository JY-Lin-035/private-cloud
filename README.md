<div align="center">

# 🐈 MeowCloud

**你的檔案，住在你的機器上。**
*Your files, on your own hardware.*

繁體中文 · [English](#english)

</div>

---

# 繁體中文

## 它是什麼

MeowCloud 是一套**自架個人雲端**：檔案存放、資料夾樹、斷點續傳上傳、垃圾桶、分享連結（含密碼保護）、資料夾整包下載、多人即時協作編輯、管理後台與一整套自動化資安防護——全部跑在你自己的一台機器上，不需要任何第三方雲服務。

## 功能總覽

| 面向 | 能力 |
|---|---|
| 📁 檔案管理 | 巢狀資料夾、搜尋、排序（時間／名稱／大小）、批次多選（移動／刪除／下載）、批次拖曳或按鈕上傳**整棵資料夾樹** |
| ⬆️ 上傳 | TUS 斷點續傳（大檔中斷可續）、0 字節檔案、即時進度；上傳即時扣額度 |
| ⬇️ 下載 | 單檔安全連結下載；資料夾／多選項目以**串流 ZIP** 即時打包（零壓縮、不落地、記憶體恆定） |
| 🔗 分享 | 四種模式自由組合：不限時／限時／**密碼保護**／限時＋密碼；資料夾分享支援線上瀏覽與逐項選取下載；密碼採 argon2 雜湊＋短效簽名通行券 |
| ✍️ 協作 | 多人即時編輯（Yjs + Monaco），自動存檔與歷史快照 |
| 👁️ 預覽／編輯（功能開關，預設關） | 雙擊開啟：文字／代碼 60+ 副檔名線上編輯（自架 Monaco，零 CDN）、Markdown 即時渲染（DOMPurify 淨化）、JSON 格式化驗證、HTML/SVG 沙箱預覽（不透明源＋代券认证）、圖片／PDF 預覽、Word 檔前端轉譯、影音 Range 串流＋瀏覽器本地快取（OPFS，再播零流量，登出即清）；新建文字檔；存檔衝突 409 偵測；垃圾桶鎖 423 |
| 🗑️ 垃圾桶 | 軟刪除／還原／永久刪除，批次操作，超過保留期（預設 30 天）自動清場，頁面即時顯示倒數政策 |
| 🛡️ 管理後台 | 使用者管理（配額／小黑屋／踢出）、功能開關（註冊、驗證信）、公告系統（導覽列跑馬燈）、IP 管控台 |
| 🚨 自動防禦 | 違規積分引擎：囓端點限流、試密碼、探測 admin → 自動「慢速通道 → 全站 429 冷卻」階梯處置；每檔分享連結×IP 錯密碼鎖；即時踢出被停用帳號；資安事件郵件警報（10 分鐘節流防轟炸） |
| 🔍 稽核 | 安全事件專用日誌；管理介面 IP 一律中段遮罩，完整資料僅存伺服器端 |

## 快速開始（一鍵部署）

需求：一台 Linux（x86_64 / ARM64）、`docker`、`git`、`nginx`、`curl`，以及 Node.js 22 與 `uv`（腳本會指引）。

```bash
git clone https://github.com/JY-Lin-035/private-cloud.git meowcloud
cd meowcloud
bash deploy/deploy.sh            # 互動選單（可自訂帳密、Port、是否自啟動）
bash deploy/deploy.sh --defaults # 或：全預設一鍵到底
```

腳本會依序完成：產生高強度隨機密碼寫入各 `.env` → 起 MySQL 8.4 ＋ Redis 7.4 容器 → 資料庫遷移 → 建立管理員帳號 → 建置前端並原子發佈 → 佈署 nginx 靜態站（含安全標頭/快取/反代）→ 安裝 systemd 使用者服務與開機自啟。

完成後管理員帳密印在 `deploy/.credentials`（600 權限，**請立即轉移並刪除**），開啟 `http://127.0.0.1:5173` 即可登入。要從外部存取，請自行掛反向代理或隧道（如 Cloudflare Tunnel）指向本機 5173（靜態）與 8000（API/WS）。

## 開發環境（手動）

```bash
# 1. 資料庫
cd db && docker compose up -d && cd ..

# 2. 後端（Python 3.12+，使用 uv）
cd backend
cp .env.example .env        # 依 db/.env 的密碼調整 DB_* / REDIS_PASSWORD
uv sync
uv run alembic upgrade head
uv run python -m app.cli.create_admin --username admin --email me@local --generate
uv run main.py              # FastAPI @ :8000

# 3. 前端
cd ../frontend
pnpm install
pnpm dev --port 5174        # 開發伺服器（生產 nginx 佔 5173）
```

測試：`cd backend && uv run pytest`（170+ 案例）。

## 設定參考（`backend/.env`）

| 變數 | 預設 | 說明 |
|---|---|---|
| `DB_* / REDIS_*` | localhost | 資料庫與 Redis 連線（含密碼） |
| `TOKEN_EXPIRE_TIME` | 30 | Session 有效分鐘數（每次活動自動續期） |
| `TRASH_RETENTION_DAYS` | 30 | 垃圾桶保留天數 |
| `TRASH_CLEANUP_INTERVAL_SECONDS` | 604800 | 自動清場排程間隔 |
| `SHARE_TICKET_TTL_SECONDS` | 900 | 分享密碼通行券效期 |
| `SEC_GLOBAL_HOURLY_LIMIT` | 5000 | 每 IP 全域請求水位 |
| `SEC_SCORE_SLOW_THRESHOLD` / `SEC_SCORE_BLOCK_THRESHOLD` | 20 / 15 | 積分觸發慢速／直接封鎖 |
| `SEC_UPLOAD_HOURLY_LIMIT` 等 | 600/300/150 | 上傳、下載、匿名分享下載之每小時量閾值 |
| `SECURITY_ALERT_ENABLED` / `SECURITY_ALERT_EMAIL` | on / SMTP 帳號 | 資安警報郵件 |
| `SMTP_*` | — | 驗證信/警報信寄送 |

## 架構

```
瀏覽器
 ├─ 靜態站      → nginx :5173  → /srv/meowcloud/current（Vite 產物，符號鏈接原子切換）
 ├─ API / WebSocket → FastAPI :8000（uvicorn）
 │                ├─ MySQL 8.4（Docker 卷）
 │                ├─ Redis 7.4（session · 限流計分 · Celery broker）
 │                └─ 本機儲存目錄（檔案以 UUID 命名，與資料庫記錄分離）
 └─（選）對外：Cloudflare Tunnel / 自建反代 → 上述兩個 port

背景行程
 ├─ celery worker       —— 驗證信、驗證碼信、資安警報信
 └─ celery worker -B    —— 排程：垃圾桶清場、用量重算（獨立佇列，與寄信互不干擾）
```

## 安全設計

- **密碼**：帳號與分享密碼一律 argon2 雜湊；比對由常量時間庫函式執行
- **Session**：Redis 伺服端儲存 + HttpOnly/Secure Cookie；停用帳號**即時**失效
- **分享通行券**：驗證密碼後發放 HMAC 簽名、綁定連結、15 分鐘過期的短效票，伺服器零狀態
- **限流與自動處置**：端點級 IP 限流 → 連結×IP 錯密碼鎖 → 積分制「慢速通道（真頻寬壓制）→ 全站 429（偽裝限流）」階梯，冷卻次數遞增（6h→24h→72h）
- **隔離**：所有查詢以擁有者為主鍵過濾；路徑參數一律清洗並限深度，杜絕穿越
- **頭部防護**：CSP／nosniff／frame-ancestors 等安全標頭；靜態檔與 API 分離部署
- **稽核**：安全事件獨立日誌；管理介面與通知郵件中 IP 一律遮罩

## 疑難排解

| 狀況 | 檢查 |
|---|---|
| 靜態站 502/404 | `readlink /srv/meowcloud/current` 是否指向有效 release |
| 一直收到 429 | 你被自己的防線鎖了：到 IP Management 解除，或等冷卻 |
| 驗證信沒送出 | `SMTP_*` 設定與 `logs/celery.log` |
| 註冊按鈕消失 | Function Control 的「開放註冊／驗證信」開關 |
| 資料庫連線失敗 | `db/.env` 密碼與容器內環境是否一致（改過要 `docker compose up -d --force-recreate db`） |

---

# English

## What is it

MeowCloud is a **self-hosted personal cloud**: file & folder management, resumable uploads, a trash bin, password-protected share links, streaming ZIP downloads, real-time collaborative editing, a full admin console, and a built-in automated security layer — all running on hardware you own.

## Feature highlights

| Area | Capability |
|---|---|
| 📁 Files | Nested folders, search, sortable list, multi-select batch actions (move / delete / download), drag-and-drop of entire folder trees |
| ⬆️ Upload | TUS resumable protocol (survives disconnects, zero-byte files supported), live progress, quota-enforced |
| ⬇️ Download | Signed one-click links; folders and multi-selections streamed as ZIP (store-mode, no temp files, constant memory) |
| 🔗 Sharing | Four combinable modes: permanent / expiring / **password-protected** / expiring + password; shared folders get online browsing with per-file selection; passwords stored as argon2 hashes behind short-lived HMAC tickets |
| ✍️ Collaboration | Multi-user editing (Yjs + Monaco) with autosave and history snapshots |
| 👁️ Preview / Edit (feature-flagged, off by default) | Double-click to open: 60+ text/code formats edited in a self-hosted Monaco (zero CDN), live Markdown preview (DOMPurify-sanitized), JSON format/validate, sandboxed HTML/SVG preview (opaque origin + single-purpose tokens), image/PDF preview, in-browser Word rendering, Range-streamed media with local OPFS cache (replays offline, purged on logout), file creation, 409 conflict detection, 423 trash locks |
| 🗑️ Trash | Soft delete, restore, batch purge, automatic cleanup past retention (30 days by default, env-driven) |
| 🛡️ Admin | User management (quota / disable / force logout), feature flags, announcement ticker, IP control panel |
| 🚨 Auto-defense | Violation scoring: endpoint abuse, password guessing, admin probing → automatic *slow-lane* (real bandwidth throttling) escalating to staged site-wide 429 cooldowns; per link×IP lockouts; instant session revocation; email security alerts with a 10-minute anti-spam cooldown |
| 🔍 Audit | Dedicated security event log; IPs are masked in every UI surface and notification |

## Quick start (one command)

Requirements: Linux (x86_64 / ARM64), `docker`, `git`, `nginx`, `curl`, plus Node.js 22 and `uv`.

```bash
git clone https://github.com/JY-Lin-035/private-cloud.git meowcloud
cd meowcloud
bash deploy/deploy.sh            # interactive: custom secrets, ports, autostart
bash deploy/deploy.sh --defaults # or: fully automatic
```

The script generates strong credentials, boots MySQL 8.4 + Redis 7.4, runs migrations, creates an admin account, builds and atomically publishes the frontend, installs a hardened nginx site, and (optionally) a systemd user service with login linger. Admin credentials land in `deploy/.credentials` (0600) — move and delete it right away. Browse to `http://127.0.0.1:5173`. Expose externally with a reverse proxy or tunnel of your choice.

## Development setup

```bash
cd db && docker compose up -d && cd ..
cd backend && cp .env.example .env && uv sync \
  && uv run alembic upgrade head \
  && uv run python -m app.cli.create_admin --username admin --email me@local --generate \
  && uv run main.py                       # API on :8000
cd ../frontend && pnpm install && pnpm dev --port 5174
```

Tests: `cd backend && uv run pytest` (170+ cases).

## Architecture

```
Browser
 ├─ Static site        → nginx :5173 → /srv/meowcloud/current (atomic symlink swap per release)
 ├─ API / WebSocket    → FastAPI :8000 (uvicorn)
 │                         ├─ MySQL 8.4        ├─ Redis 7.4 (sessions · counters · broker)
 │                         └─ local blob store (UUID filenames, DB-referenced)
 └─ (optional) edge: Cloudflare Tunnel / your own reverse proxy

Background
 ├─ celery worker     — verification & alert emails
 └─ celery worker -B  — scheduled trash purge & storage recalculation (isolated queue)
```

## Security design

- argon2 password hashing (accounts **and** share links); constant-time verification
- server-side sessions in Redis (HttpOnly/Secure cookies); disabling an account revokes it instantly
- password-protected shares issue HMAC-signed, link-bound, expiring tickets — zero server state
- layered auto-defense: per-endpoint IP limits → per link×IP lockout → violation-score slow lane (genuine ASGI bandwidth pacing) → staged site-wide 429 cooldowns (6h/24h/72h)
- ownership-scoped queries and sanitized path resolution everywhere (no traversal)
- hardened response headers (CSP, nosniff, frame-ancestors…); static and API planes deployed separately
- dedicated security event log; masked IPs in UI and email

## Troubleshooting

| Symptom | Check |
|---|---|
| Static site 502/404 | `readlink /srv/meowcloud/current` points at a valid release |
| You keep getting 429 | your IP hit its own defense ladder — release it in IP Management or wait out cooldown |
| No verification emails | `SMTP_*` settings and `logs/celery.log` |
| Register button missing | Feature flags: *allow registration* / *verification email* |
| DB connection failed | `db/.env` passwords vs. running containers (`docker compose up -d --force-recreate`) |

## License

No license file has been declared yet — add a `LICENSE` to define reuse terms before publishing.
