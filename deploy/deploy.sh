#!/usr/bin/env bash
# meowcloud one-click deployer
#   ./deploy.sh              interactive menu
#   ./deploy.sh --defaults   fully automatic with safe defaults (aborts on existing install unless --force)
#   ./deploy.sh --check-only dependency check only
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDO=""
if [ "$(id -u)" != "0" ]; then
  command -v sudo >/dev/null 2>&1 || { echo "需要 root 或 sudo"; exit 1; }
  SUDO=sudo
fi
MODE=""
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --defaults) MODE=defaults ;;
    --custom) MODE=custom ;;
    --check-only) MODE=check ;;
    --force) FORCE=1 ;;
    *) echo "unknown option $1"; exit 1 ;;
  esac
  shift
done

randpw() { openssl rand -hex 32; }
ask() { local prompt="$1" dflt="$2" v=""
  if [ "$MODE" = "custom" ]; then read -r -p "$prompt [$dflt]: " v || true; fi
  echo "${v:-$dflt}"
}
ask_secret() { local prompt="$1" dflt="$2" v=""
  if [ "$MODE" = "custom" ]; then read -r -s -p "$prompt (Enter=random): " v || true; echo >&2; fi
  echo "${v:-$dflt}"
}
yesno() { local prompt="$1" dflt="${2:-Y}" v=""
  if [ "$MODE" = "custom" ]; then read -r -p "$prompt [$dflt]: " v || true; v=${v:-$dflt}; fi
  case "${v:-$dflt}" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
ask_bool() { local prompt="$1" v=""
  if [ "$MODE" != "custom" ]; then echo Y; return; fi
  read -r -p "$prompt [Y/n]: " v || true
  echo "${v:-Y}"
}
yesno_or() { case "${1:-Y}" in [Yy]*) return 0 ;; *) return 1 ;; esac; }

check_deps() {
  local missing=0
  for c in git nginx openssl; do
    command -v "$c" >/dev/null || { echo "缺少相依: $c"; missing=1; }
  done
  command -v uv >/dev/null || { echo "缺少相依: uv (https://docs.astral.sh/uv/)"; missing=1; }
  command -v pnpm >/dev/null || { echo "缺少相依: pnpm"; missing=1; }
  command -v envsubst >/dev/null || { echo "缺少相依: envsubst（Debian/Ubuntu: apt install gettext-base；Arch: pacman -S gettext）"; missing=1; }
  command -v node >/dev/null || { echo "缺少相依: node"; missing=1; }
  id -nG | grep -qw docker || echo "WARN: 目前使用者不在 docker 群組（compose 步驟可能需 sudo）"
  [ "$missing" = 0 ] && echo "依賴檢查通過"
  return $missing
}

if [ "$MODE" = "check" ]; then exit $(check_deps >/dev/null 2>&1; echo $?); fi
if [ -z "$MODE" ]; then
  echo "=== meowcloud deploy ==="
  echo "  [1] 一鍵部署（全預設值）"
  echo "  [2] 自定義部署"
  echo "  [3] 僅檢查環境相依"
  read -r -p "選擇 [1]: " sel
  case "${sel:-1}" in
    1) MODE=defaults ;; 2) MODE=custom ;; 3) MODE=check; check_deps; exit ;;
    *) echo "invalid"; exit 1 ;;
  esac
fi

check_deps

# ---------- existing-install guard ----------
EXISTS=0
for f in "$REPO/backend/.env" "$REPO/db/.env" "$REPO/frontend/.env"; do
  [ -f "$f" ] && EXISTS=1
done
if [ "$EXISTS" = 1 ] && [ "$FORCE" = 0 ]; then
  echo "偵測到既有部署（.env 已存在）。"
  echo "為避免覆寫既有密碼／SHARE_TICKET_SECRET（會中斷服務與分享連結），已中止。"
  echo "如確定要重新產生設定，請加 --force。"
  exit 1
fi

# ---------- configuration ----------
DB_NAME=$(ask "資料庫名稱" "my_database")
DB_USER=$(ask "資料庫帳號" "mysql")
DB_PASSWORD=$(ask_secret "資料庫密碼" "$(randpw)")
MYSQL_ROOT_PASSWORD=$(ask_secret "MySQL root 密碼" "$(randpw)")
REDIS_PASSWORD=$(ask_secret "Redis 密碼" "$(randpw)")
BACKEND_PORT=$(ask "後端 port" "8000")
STATIC_PORT=$(ask "靜態站 port" "5173")
ADMIN_USERNAME=$(ask "管理員帳號" "meowadmin")
ADMIN_EMAIL=$(ask "管理員 email" "admin@localhost.local")
ADMIN_PASSWORD=$(ask_secret "管理密碼" "$(randpw | cut -c1-12)Aa1!@#")
START_DB=$(ask_bool "由本腳本啟動 Docker DB/Redis?")
DB_HOST=127.0.0.1; DB_PORT=3306; REDIS_HOST=127.0.0.1; REDIS_PORT=6379
if [ "$MODE" = "custom" ] && ! yesno_or "$START_DB"; then
  DB_HOST=$(ask "外部 MySQL host" "127.0.0.1")
  DB_PORT=$(ask "外部 MySQL port" "3306")
  REDIS_HOST=$(ask "外部 Redis host" "127.0.0.1")
  REDIS_PORT=$(ask "外部 Redis port" "6379")
fi
INSTALL_NGINX=$(ask_bool "安裝 nginx 靜態站?")
INSTALL_SYSTEMD=$(ask_bool "安裝 systemd 自啟動?")

# Public URLs the browser will use for the API / WebSocket. Defaults are
# loopback (local-only install). Behind a tunnel/domain set these via env or
# the custom menu, otherwise the built SPA would try to reach the visitor's
# own localhost.
API_PUBLIC="${MEOW_API_BASE_URL:-}"
WS_PUBLIC="${MEOW_WS_BASE_URL:-}"
if [ "$MODE" = custom ]; then
  API_PUBLIC=$(ask "公開 API base URL" "${API_PUBLIC:-http://127.0.0.1:$BACKEND_PORT}")
  WS_PUBLIC=$(ask "公開 WS base URL（Enter=自動依 API 推導）" "${WS_PUBLIC:-}")
fi
[ -n "$API_PUBLIC" ] || API_PUBLIC="http://127.0.0.1:$BACKEND_PORT"
if [ -z "$WS_PUBLIC" ]; then
  case "$API_PUBLIC" in
    https://*) WS_PUBLIC="wss://${API_PUBLIC#https://}" ;;
    http://*)  WS_PUBLIC="ws://${API_PUBLIC#http://}" ;;
    *)         WS_PUBLIC="$API_PUBLIC" ;;
  esac
fi
SMTP_HOST=""; SMTP_USER=""; SMTP_PASSWORD=""; SMTP_FROM=""
if [ "$MODE" = custom ]; then
  read -r -p "SMTP host（Enter 跳過）: " SMTP_HOST || true
  if [ -n "$SMTP_HOST" ]; then
    read -r -p "SMTP user: " SMTP_USER; read -r -s -p "SMTP password: " SMTP_PASSWORD; echo
    read -r -p "SMTP from: " SMTP_FROM
  fi
fi

CREDS="$REPO/deploy/.credentials"

backup_if_exists() { [ -f "$1" ] && cp -a "$1" "$1.bak.$(date +%s)" && echo "backup: $1.*"; return 0; }

write_files() {
  mkdir -p "$REPO/db"
  backup_if_exists "$REPO/db/.env"
  cat > "$REPO/db/.env" <<EOF
MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASSWORD
MYSQL_PASSWORD=$DB_PASSWORD
REDIS_CONF=$REPO/db/redis.conf
EOF
  chmod 600 "$REPO/db/.env"

  backup_if_exists "$REPO/db/redis.conf"
  cat > "$REPO/db/redis.conf" <<EOF
requirepass $REDIS_PASSWORD
save 60 1
loglevel warning
appendonly no
EOF
  chmod 600 "$REPO/db/redis.conf"

  backup_if_exists "$REPO/backend/.env"
  cat > "$REPO/backend/.env" <<EOF
APP_URL=$API_PUBLIC
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
REDIS_HOST=$REDIS_HOST
REDIS_PORT=$REDIS_PORT
REDIS_DB=0
REDIS_PASSWORD=$REDIS_PASSWORD
SHARE_TICKET_SECRET=$(randpw)
SMTP_HOST=$SMTP_HOST
SMTP_PORT=587
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
EOF
  chmod 600 "$REPO/backend/.env"

  backup_if_exists "$REPO/frontend/.env"
  cat > "$REPO/frontend/.env" <<EOF
VITE_API_BASE_URL=$API_PUBLIC
VITE_WS_BASE_URL=$WS_PUBLIC
EOF
  chmod 600 "$REPO/frontend/.env"

  cat > "$CREDS" <<EOF
# meowcloud deploy credentials - generated $(date '+%F %T')
mysql root : $MYSQL_ROOT_PASSWORD
mysql app  : $DB_USER / $DB_PASSWORD
redis      : $REDIS_PASSWORD
admin      : $ADMIN_USERNAME / $ADMIN_PASSWORD
EOF
  chmod 600 "$CREDS"
  echo "設定檔與憑證寫入完成（deploy/.credentials）"
}

start_db() {
  echo "=== 啟動 DB/Redis 容器 ==="
  command -v docker >/dev/null 2>&1 || { echo "此模式需要 docker，但未安裝"; exit 1; }
  ( cd "$REPO/db" && docker compose up -d )
  echo "等待 MySQL 就緒..."
  for _ in $(seq 1 60); do
    docker exec mysql_service mysqladmin -uroot -p"$MYSQL_ROOT_PASSWORD" ping >/dev/null 2>&1 && break
    sleep 2
  done
  echo "等待 Redis 就緒..."
  for _ in $(seq 1 30); do
    [ "$(docker exec redis_service redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping 2>/dev/null)" = PONG ] && break
    sleep 2
  done
  docker exec mysql_service mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4;" 2>/dev/null
}

migrate_and_admin() {
  echo "=== 同步後端依賴並執行遷移 ==="
  ( cd "$REPO/backend" && uv sync && uv run alembic upgrade head )
  echo "=== 建立管理員 ==="
  ( cd "$REPO/backend" && uv run python -W ignore -m app.cli.create_admin --username "$ADMIN_USERNAME" --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" ) || \
    echo "管理員建立失敗（可能已存在），可稍後手動執行 app.cli.create_admin"
}

build_and_publish_frontend() {
  echo "=== 建置前端 ==="
  ( cd "$REPO/frontend" && pnpm install --frozen-lockfile && pnpm build )
  local ng_group g
  ng_group="$(awk '/^[[:space:]]*user[[:space:]]/{gsub(";","",$2); print $2; exit}' /etc/nginx/nginx.conf 2>/dev/null)"
  if [ -z "$ng_group" ] || ! getent group "$ng_group" >/dev/null 2>&1; then
    ng_group=""
    for g in www-data nginx http; do
      if getent group "$g" >/dev/null 2>&1; then ng_group="$g"; break; fi
    done
  fi
  [ -n "$ng_group" ] || ng_group="$(id -gn)"
  $SUDO install -d -o "$(id -u)" -g "$ng_group" -m 755 /srv/meowcloud/releases
  local dest="/srv/meowcloud/releases/$(date +%Y%m%d-%H%M%S)-deploy"
  mkdir -p "$dest" && cp -a "$REPO/frontend/dist/." "$dest/"
  ln -sfn "$dest" /srv/meowcloud/.current.tmp && mv -Tf /srv/meowcloud/.current.tmp /srv/meowcloud/current
  echo "前端已發佈: $dest"
}

install_nginx() {
  echo "=== 安裝 nginx 靜態站（port $STATIC_PORT）==="
  $SUDO install -d -m 755 /etc/nginx/snippets
  $SUDO install -d -m 755 /etc/nginx/api-gw
  $SUDO tee /etc/nginx/api-gw/00-logformat.conf >'/dev/null' <<'EOF'
log_format cfip '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" "$http_x_forwarded_for" cf=$http_cf_connecting_ip';
EOF
  env BACKEND_PORT="$BACKEND_PORT" envsubst '$BACKEND_PORT' <<'EOF' | $SUDO tee /etc/nginx/snippets/meow_security_headers.conf >'/dev/null'
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' https://meowcloud-api.jun.org.uk wss://meowcloud-api.jun.org.uk https://cloudflareinsights.com; worker-src 'self' blob:; child-src 'self' blob:; frame-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
EOF
  env BACKEND_PORT="$BACKEND_PORT" STATIC_PORT="$STATIC_PORT" envsubst '$BACKEND_PORT $STATIC_PORT' <<'EOF' | $SUDO tee /etc/nginx/api-gw/spa.conf >'/dev/null'
upstream meow_backend {
    server 127.0.0.1:$BACKEND_PORT;
    keepalive 64;
}

server {
    listen 127.0.0.1:$STATIC_PORT;
    listen [::1]:$STATIC_PORT;
    server_name _;

    root /srv/meowcloud/current;
    index index.html;

    access_log /var/log/nginx/static-access.log cfip;

    sendfile on; tcp_nopush on; tcp_nodelay on;
    gzip on; gzip_comp_level 5; gzip_min_length 1024; gzip_vary on;
    gzip_types text/css application/javascript application/json image/svg+xml application/wasm;
    open_file_cache max=2000 inactive=120s;
    open_file_cache_valid 300s;
    open_file_cache_errors on;

    server_tokens off;
    client_max_body_size 1m;
    location ~ /\. { deny all; }
    include /etc/nginx/snippets/meow_security_headers.conf;

    location /assets/ {
        include /etc/nginx/snippets/meow_security_headers.conf;
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
        limit_except GET HEAD { deny all; }
    }
    location = /index.html {
        include /etc/nginx/snippets/meow_security_headers.conf;
        add_header Cache-Control "no-cache, must-revalidate";
    }

    location /api/ {
        client_max_body_size 64m;
        proxy_pass http://meow_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s; proxy_send_timeout 60s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 43200s; proxy_send_timeout 43200s;
    }

    location = /meow-sw.js {
        include /etc/nginx/snippets/meow_security_headers.conf;
        open_file_cache off;
        add_header Cache-Control "no-store";
        try_files $uri =404;
    }
    location = /version.json {
        include /etc/nginx/snippets/meow_security_headers.conf;
        open_file_cache off;
        add_header Cache-Control "no-store";
        try_files $uri =404;
    }
    location / {
        include /etc/nginx/snippets/meow_security_headers.conf;
        open_file_cache off;
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ /index.html;
    }
}
EOF
  if ! grep -q 'include /etc/nginx/api-gw' /etc/nginx/nginx.conf; then
    $SUDO sed -i '\|^http {|a\    include /etc/nginx/api-gw/*.conf;' /etc/nginx/nginx.conf
  fi
  if grep -q '^worker_processes  1;' /etc/nginx/nginx.conf; then
    $SUDO sed -i 's/^worker_processes  1;/worker_processes auto;/' /etc/nginx/nginx.conf
  fi
  $SUDO nginx -t
  if [ -d /run/systemd/system ]; then
    if systemctl is-active --quiet nginx; then $SUDO systemctl reload nginx; else $SUDO systemctl enable --now nginx; fi
  else
    pgrep -x nginx >/dev/null 2>&1 && $SUDO nginx -s reload || $SUDO nginx
  fi
  echo "nginx 完成"
}

install_systemd() {
  echo "=== 安裝 systemd user 服務 ==="
  local unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir"
  local node_bin
  node_bin="$(dirname "$(command -v node)")"
  cat > "$unit_dir/meowcloud.service" <<EOF
[Unit]
Description=meowcloud (backend, celery, cleanup, frontend deploy)
After=network-online.target docker.service

[Service]
Type=simple
ExecStart=/usr/bin/env bash $REPO/deploy/meowcloud-run.sh
Restart=on-failure
Environment=PATH=$HOME/.local/bin:$HOME/.local/share/pnpm:$node_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=default.target
EOF
  if [ ! -d /run/systemd/system ]; then
    echo "未偵測到 systemd：unit 已寫入 $unit_dir/meowcloud.service，請手動執行 bash $REPO/deploy/meowcloud-run.sh 啟動"
    return 0
  fi
  systemctl --user daemon-reload
  systemctl --user enable --now meowcloud.service
  [ -d /run/systemd/system ] && $SUDO loginctl enable-linger "$(id -un)" || true
  echo "systemd 完成（開機/登入即自動啟動）"
}

write_files
if yesno_or "$START_DB"; then start_db; fi
migrate_and_admin
build_and_publish_frontend
if yesno_or "$INSTALL_NGINX"; then install_nginx; fi
if yesno_or "$INSTALL_SYSTEMD"; then install_systemd; fi

echo
echo "=== 部署完成 ==="
echo "靜態站   : http://127.0.0.1:$STATIC_PORT"
echo "API      : http://127.0.0.1:$BACKEND_PORT"
echo "管理帳號 : $ADMIN_USERNAME（密碼見 $CREDS，請立即轉移並刪除該檔）"
echo "外部存取請自行設定反向代理或隧道（指向 127.0.0.1:$STATIC_PORT / :$BACKEND_PORT）"
