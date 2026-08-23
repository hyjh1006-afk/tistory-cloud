#!/bin/bash
# 괴담 글 1편 생성 래퍼 — 예약 작업이 부르는 유일한 명령.
# 사용: scripts/gwidam.sh two_sentence | nosleep
set -euo pipefail

ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
SECRETS="/Users/oddo/Developer/oddo/threads-kitchen/.env"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"

# 제미나이·쿠팡 키는 집밥 프로젝트 비밀파일에서 빌려 쓴다 (값은 화면에 찍지 않는다)
if [ -f "$SECRETS" ]; then
  for k in GEMINI_API_KEY COUPANG_ACCESS_KEY COUPANG_SECRET_KEY; do
    v="$(grep -m1 "^${k}=" "$SECRETS" | cut -d= -f2- | tr -d '"'"'"'\r')" || true
    [ -n "${v:-}" ] && export "$k=$v"
  done
fi

# 번호·사용기록 보존용 (gh 로그인 토큰 재사용)
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
export GITHUB_TOKEN

exec "$ROOT/.venv/bin/python" "$ROOT/scripts/run_gwidam.py" "$@"
