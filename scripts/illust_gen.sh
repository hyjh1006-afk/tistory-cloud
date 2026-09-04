#!/bin/bash
# 글 하나에 붙일 삽화를 codex-image 로 생성한다.
# 사용: scripts/illust_gen.sh <글번호> "<장면 설명>"
#   파일명은 글 제목(위험문자 치환)으로, assets/illustrations/ 에 저장된다.
set -euo pipefail

ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
OUT="$ROOT/assets/illustrations"
GEN="$HOME/.claude/plugins/cache/codex-image-in-cc/codex-image/0.2.0/scripts/codex-image.mjs"
MAP="${ILLUST_MAP:-/tmp/postmap.txt}"

ID="${1:?글번호}"
SCENE="${2:?장면 설명}"

TITLE="$(awk -F'\t' -v id="$ID" '$1==id{print $2; exit}' "$MAP")"
[ -n "$TITLE" ] || { echo "✗ $ID 제목을 못 찾음 ($MAP)"; exit 1; }
# 파일명: 제목에서 / ? : * " < > | 를 없애거나 바꾼다
NAME="$(printf '%s' "$TITLE" | sed 's#/#-#g; s#[?:*"<>|]##g; s#  *# #g')"
DEST="$OUT/${NAME}.png"

if [ -f "$DEST" ]; then echo "· 이미 있음: $NAME.png"; exit 0; fi

# 시리즈 공통 화풍 — 세 시리즈 전부 이 톤으로 통일한다
STYLE="어두운 사진풍 실사(포토리얼), 35mm 필름 그레인, 탈색된 청록/회색 색조, 깊은 그림자, 약한 비네팅, 얕은 심도, 조용하고 불안한 분위기. 사람 없음, 얼굴 없음, 피·시체·훼손 없음, 글자·간판·로고·워터마크 없음. 가로형 16:9."

mkdir -p "$OUT"
echo "▶ $ID : $NAME"
node "$GEN" generate "${SCENE} ${STYLE} 저장 위치: ${OUT}/ , 저장 파일명: __tmp_illust.png" 2>&1 | tail -3

if [ -f "$OUT/__tmp_illust.png" ]; then
  mv "$OUT/__tmp_illust.png" "$DEST"
  echo "  ✓ $DEST"
else
  echo "  ✗ 생성 실패"; exit 1
fi
