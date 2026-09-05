#!/bin/bash
# 이미 올라간 글의 제목 바로 밑에 삽화를 넣고, 예약 설정을 유지한 채 다시 저장한다.
# 사용: scripts/illust_insert.sh <글번호>
#
# 핵심(2026-09-05 여행 블로그 세션에서 배움):
#   #attach-layer-btn → #attach-image 에 파일을 물리면 업로드가 안 걸린다.
#   **툴바 "첨부" → 드롭다운 "사진"** 으로 생기는 input 이라야 업로드→본문 삽입까지 된다.
set -euo pipefail

A="$HOME/.claude/tools/screen/aside.sh"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
MAP="${ILLUST_MAP:-/tmp/postmap.txt}"
ID="${1:?글번호}"
TAB="~.*newpost/${ID}"

TITLE="$(awk -F'\t' -v id="$ID" '$1==id{print $2; exit}' "$MAP")"
[ -n "$TITLE" ] || { echo "✗ $ID 제목을 못 찾음"; exit 1; }
NAME="$(printf '%s' "$TITLE" | sed 's#/#-#g; s#[?:*"<>|]##g')"
IMG="$ROOT/assets/illustrations/${NAME}.png"
[ -f "$IMG" ] || { echo "✗ 삽화 없음: ${NAME}.png"; exit 1; }

echo "▶ /$ID  ${NAME:0:40}"

LOCK=/tmp/tistory-editor.lock
for i in $(seq 1 60); do
  mkdir "$LOCK" 2>/dev/null && break
  [ -n "$(find "$LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ] && { rmdir "$LOCK" 2>/dev/null || true; continue; }
  sleep 20
done
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

"$A" close "/manage/newpost/${ID}" >/dev/null 2>&1 || true
sleep 1
"$A" open "https://tester188.tistory.com/manage/post/${ID}" >/dev/null
sleep 12
ready=$("$A" eval "$TAB" '(()=>(!!document.querySelector("#post-title-inp")&&typeof window.tinymce==="object"))()' 2>/dev/null || echo timeout)
if [ "$ready" != "true" ]; then
  "$HOME/.claude/tools/screen/aside_confirm.sh" cancel >/dev/null 2>&1 || true
  sleep 2
  ready=$("$A" eval "$TAB" '(()=>(!!document.querySelector("#post-title-inp")&&typeof window.tinymce==="object"))()' 2>/dev/null || echo timeout)
fi
[ "$ready" = "true" ] || { echo "  ✗ 편집기 안 뜸 ($ready)"; exit 1; }

# 이미 삽화가 있으면 건너뛴다 (중복 삽입 방지)
have=$("$A" eval "$TAB" 'String(tinymce.activeEditor.getBody().querySelectorAll("figure[data-ke-type=image] img").length)' 2>/dev/null | tr -d '"')
if [ "${have:-0}" != "0" ]; then echo "  · 이미 이미지 ${have}개 — 건너뜀"; exit 0; fi

# 1) 툴바 첨부 → 2) 사진
"$A" eval "$TAB" '(()=>{const b=[...document.querySelectorAll(".mce-btn")].find(e=>e.getAttribute("aria-label")==="첨부"&&e.offsetParent!==null);(b.querySelector("button")||b).click();return 1})()' >/dev/null
sleep 2
"$A" eval "$TAB" '(()=>{const it=[...document.querySelectorAll(".mce-menu-item")].find(e=>(e.innerText||"").trim()==="사진"&&e.offsetParent!==null);if(it)it.click();return 1})()' >/dev/null
sleep 3

# 3) 파일 물리기
"$A" file "$TAB" 'input[type=file][accept^="image"]' "$IMG" >/dev/null

# 4) 업로드 완료 대기
ok=0
for i in $(seq 1 12); do
  sleep 4
  n=$("$A" eval "$TAB" 'String(tinymce.activeEditor.getBody().querySelectorAll("figure[data-ke-type=image] img[src*=kakaocdn]").length)' 2>/dev/null | tr -d '"')
  [ "${n:-0}" != "0" ] && { ok=1; break; }
done
[ "$ok" = "1" ] || { echo "  ✗ 업로드 실패"; exit 1; }

# 5) 제목(h2) 바로 밑으로 옮기기
moved=$("$A" eval "$TAB" '(()=>{const ed=tinymce.activeEditor,b=ed.getBody();const f=b.querySelector("figure[data-ke-type=image]");const h=b.querySelector("h2");if(!f||!h)return "요소없음";h.insertAdjacentElement("afterend",f);ed.setDirty(true);ed.fire("change");return [...b.children].slice(0,3).map(e=>e.tagName).join(">")})()' 2>/dev/null | tr -d '"')
echo "  · 배치: $moved"

# 6) 완료 → 발행 (예약 설정은 건드리지 않는다)
when=$("$A" eval "$TAB" '(async()=>{[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="완료").click();await new Promise(r=>setTimeout(r,3000));const d=[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim()));return (d?d.textContent.trim():"?")+" "+((document.getElementById("dateHour")||{}).value||"")+":"+((document.getElementById("dateMinute")||{}).value||"")})()' 2>/dev/null | tr -d '"')
echo "  · 예약 유지: $when"
"$A" eval "$TAB" '(async()=>{const b=[...document.querySelectorAll("button")].find(x=>/발행|저장/.test(x.textContent)&&!/임시/.test(x.textContent));b.click();await new Promise(r=>setTimeout(r,4000));return 1})()' >/dev/null 2>&1 || true

# 7) CAPTCHA 가 뜨면 사람이 풀 때까지 기다린다 (자동으로 풀지 않는다)
for i in $(seq 1 60); do
  sleep 5
  alive=$("$A" tabs 2>/dev/null | grep -ci "newpost/${ID}" || echo 0)
  [ "$alive" = "0" ] && break
  cap=$("$A" eval "$TAB" '(()=>document.body.innerText.includes("정답을 입력해주세요")?"y":"n")()' 2>/dev/null | tr -d '"')
  [ "$cap" = "y" ] && { [ "$i" = "1" ] && echo "  ⏸ CAPTCHA — 사람이 풀어주기를 기다리는 중"; continue; }
done

# 8) 저장 확인 — 확인용 목록 탭이 없으면 열고 본다
if [ "$("$A" tabs 2>/dev/null | grep -ci 'manage/posts')" = "0" ]; then
  "$A" open "https://tester188.tistory.com/manage/posts/" >/dev/null 2>&1 || true
  sleep 6
fi
saved=$("$A" eval "~.*manage/posts" "(async()=>{const r=await fetch('/${ID}',{credentials:'include'});const t=await r.text();const d=new DOMParser().parseFromString(t,'text/html');const c=d.querySelector('.entry-content, .tt_article_useless_p_margin, .article_view');return String(c?c.querySelectorAll('img').length:-1)})()" 2>/dev/null | tr -d '"')
if [ "${saved:-0}" -ge 1 ] 2>/dev/null; then echo "  ✓ 저장 확인 (본문 이미지 ${saved}개)"; else echo "  ✗ 저장 확인 실패 (이미지 ${saved})"; exit 1; fi
