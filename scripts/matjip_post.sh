#!/bin/bash
# 맛집 후기 1편 발행 — 사용: scripts/matjip_post.sh <글.json> [--dry-run]  (형식·종료코드는 matjip_post.py 머리말)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/matjip_post.py" "$@"
