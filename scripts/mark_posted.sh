#!/bin/bash
# 티스토리에 올린 글을 GitHub 대기 목록에서 지운다.
# 사용: scripts/mark_posted.sh 20260823_204855_451-460.json [...]
set -euo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token)"; export GITHUB_TOKEN
cd "$ROOT"
exec "$ROOT/.venv/bin/python" - "$@" <<'PY'
import sys
sys.path.insert(0, ".")
import github_state
targets = set(sys.argv[1:])
outputs = github_state.list_outputs()
for o in outputs:
    if not targets or o["_name"] in targets:
        github_state.delete_output(o["_name"], o["_sha"])
        print("대기목록에서 제거:", o["_name"])
print("남은 대기:", [o["_name"] for o in github_state.list_outputs()])
PY
