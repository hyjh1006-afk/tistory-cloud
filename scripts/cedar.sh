#!/bin/bash
# 시더빌 리마스터 도구 래퍼. 사용: scripts/cedar.sh build <입력.txt>
set -euo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token)"; export GITHUB_TOKEN
cd "$ROOT"
case "${1:-}" in
  build) shift; exec "$ROOT/.venv/bin/python" "$ROOT/scripts/cedar_build.py" "$@" ;;
  *) echo "사용: cedar.sh build <입력.txt>" >&2; exit 2 ;;
esac
