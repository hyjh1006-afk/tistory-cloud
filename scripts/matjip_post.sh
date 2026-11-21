#!/bin/bash
# 맛집 후기 1편 발행 — 사용: scripts/matjip_post.sh <글.json> [--dry-run]  (형식·종료코드는 matjip_post.py 머리말)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
cd "$ROOT"
# 쿠팡파트너스 키는 괴담처럼 집밥 프로젝트 비밀파일에서 빌려 쓴다(값은 찍지 않는다)
SECRETS="/Users/oddo/Developer/oddo/threads-kitchen/.env"
if [ -f "$SECRETS" ]; then
  for k in COUPANG_ACCESS_KEY COUPANG_SECRET_KEY; do
    v="$(grep -m1 "^${k}=" "$SECRETS" | cut -d= -f2- | tr -d '"'"'"'\r')" || true
    [ -n "${v:-}" ] && export "$k=$v"
  done
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/matjip_post.py" "$@"
