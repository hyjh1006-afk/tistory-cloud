#!/bin/bash
# 이미 올라간 쿠팡 링크 글 맨 위에 고지 상자 — 사용: scripts/add_disclosure.sh <글번호...> (설명은 add_disclosure.py 머리말)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/add_disclosure.py" "$@"
