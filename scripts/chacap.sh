#!/bin/bash
# CHACAP — 티스토리 CAPTCHA 화면을 대표님 텔레그램으로 보내고, 답장 글자를 입력칸에 옮겨 적는다.
#   캡챠를 스스로 풀지 않는다 — 답은 대표님이 보낸 글자뿐이다. 상세는 scripts/chacap.py 머리말.
# 사용: scripts/chacap.sh setup | ping | selftest | relay (--tid <id> | --match <정규식>) [--label 이름]
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/chacap.py" "$@"
