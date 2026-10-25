#!/usr/bin/env bash
# meowcloud runtime entry installed by deploy.sh (systemd ExecStart target).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO/backend"
FRONTEND_DIR="$REPO/frontend"
LOG_DIR="${MEOWCLOUD_LOG_DIR:-$REPO/logs}"
DEPLOY_BASE="/srv/meowcloud"
RELEASES_DIR="$DEPLOY_BASE/releases"
CURRENT_LINK="$DEPLOY_BASE/current"

mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" 2>/dev/null || true
PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start_service() {
  local name="$1" dir="$2" cmd="$3" log="$4"
  ( cd "$dir" && exec $cmd ) >>"$log" 2>&1 &
  PIDS+=("$!")
  echo "started $name (pid $!)"
}

deploy_frontend() {
  local sha stamp dest
  if ! ( cd "$FRONTEND_DIR" && pnpm build ) >>"$LOG_DIR/frontend.log" 2>&1; then
    echo "[deploy] build failed, serving previous release" >>"$LOG_DIR/frontend.log"
    return 0
  fi
  sha=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo nogit)
  stamp="$(date +%Y%m%d-%H%M%S)-$sha"
  dest="$RELEASES_DIR/$stamp"
  mkdir -p "$dest" 2>/dev/null || { echo "[deploy] $RELEASES_DIR not writable" >>"$LOG_DIR/frontend.log"; return 0; }
  if cp -a "$FRONTEND_DIR/dist/." "$dest/" 2>>"$LOG_DIR/frontend.log"; then
    { ln -sfn "$dest" "$DEPLOY_BASE/.current.tmp" && mv -Tf "$DEPLOY_BASE/.current.tmp" "$CURRENT_LINK"; } || true
    ls -1dt "$RELEASES_DIR"/*/ 2>/dev/null | tail -n +4 | xargs -r rm -rf || true
  fi
  return 0
}

start_service backend  "$BACKEND_DIR" "uv run main.py" "$LOG_DIR/backend.log"
start_service celery   "$BACKEND_DIR" "uv run celery -A app.tasks.email_tasks worker --loglevel=info" "$LOG_DIR/celery.log"
start_service cleanup  "$BACKEND_DIR" "uv run celery -A app.tasks.cleanup_tasks worker -B -Q cleanup --loglevel=info -s $BACKEND_DIR/celerybeat-cleanup.db" "$LOG_DIR/celery-cleanup.log"
deploy_frontend
wait
