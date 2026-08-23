#!/bin/bash
# 아직 티스토리에 안 올린 글 목록.
set -euo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token)"; export GITHUB_TOKEN
cd "$ROOT"
exec "$ROOT/.venv/bin/python" - <<'PY'
import sys
sys.path.insert(0, ".")
import github_state
rows = github_state.list_outputs()
if not rows:
    print("대기 중인 글 없음")
for o in rows:
    print(f"{o['_name']}\t{o.get('mode','?')}\t{o.get('created_at','')}\t{o.get('title','')}")
PY
