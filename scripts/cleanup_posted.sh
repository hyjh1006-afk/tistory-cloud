#!/bin/bash
# 티스토리에 이미 올라간 글의 로컬 데이터를 지워 맥 용량을 관리한다 — 클로드 토큰 0. (2026-10-18 대표님 지시)
# publish_waiting.sh 가 정상 종료(0)하면 끝에 자동으로 부른다. 혼자 돌려도 된다.
#
# 지우는 것: state/local_outputs/ 중 대기 목록(GitHub)에 없는 것 · output/reddit_horror_* · logs/*.jpg · 30일 지난 logs/*.log
# 남기는 것: 대기 중인 글 · 작업 파일(chatgpt_prompt.txt·translation_result.txt·pending_posts.json) · 깃에 커밋된 것 전부
# 안전장치: 대기 목록을 못 읽으면 local_outputs 는 건드리지 않는다(아직 안 올린 글을 지우지 않게).
set -uo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
cd "$ROOT"
before=$(du -sk . | cut -f1)

if waiting="$("$ROOT/scripts/list_waiting.sh" 2>/dev/null)"; then
  names="$(printf '%s\n' "$waiting" | cut -f1)"
  n=0
  for f in state/local_outputs/*.json; do
    [ -e "$f" ] || continue
    if ! printf '%s\n' "$names" | grep -qxF "$(basename "$f")"; then rm -f "$f"; n=$((n+1)); fi
  done
  echo "정리: 올라간 글 로컬 사본 ${n}개 삭제"
else
  echo "정리: 대기 목록을 못 읽어 local_outputs 는 건너뜀"
fi

rm -f output/reddit_horror_* logs/*.jpg
find logs -maxdepth 1 -name '*.log' -mtime +30 -delete 2>/dev/null || true

after=$(du -sk . | cut -f1)
echo "정리: $(( (before-after)/1024 ))MB 확보 (폴더 $(du -sh . | cut -f1))"
