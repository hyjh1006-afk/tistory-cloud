#!/bin/bash
# 맛집 후기 도우미 — 사용법은 scripts/matjip.py 머리말. 데이터는 레포 밖 ~/.local/share/oddo-matjip (공개 레포라서).
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
# Pillow 가 있는 파이썬(레포 .venv 에는 없다)
PY=/opt/homebrew/bin/python3
exec "$PY" "$ROOT/scripts/matjip.py" "$@"
