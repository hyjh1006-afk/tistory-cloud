#!/bin/bash
# 이미 올린 글을 새 번역으로 다시 만든다. 사용: scripts/rebuild.sh output/rebuild_451.json
set -euo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
SECRETS="/Users/oddo/Developer/oddo/threads-kitchen/.env"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
if [ -f "$SECRETS" ]; then
  for k in GEMINI_API_KEY COUPANG_ACCESS_KEY COUPANG_SECRET_KEY; do
    v="$(grep -m1 "^${k}=" "$SECRETS" | cut -d= -f2- | tr -d '"'"'"'\r')" || true
    [ -n "${v:-}" ] && export "$k=$v"
  done
fi
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token)"; export GITHUB_TOKEN
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/rebuild_post.py" "$@"
