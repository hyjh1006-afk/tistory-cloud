#!/bin/bash
# 이미 삽화가 있는 글에서 **그림 위치만** 제목(h2) 바로 밑으로 고쳐 다시 저장한다.
#   사용: illust_fix_pos.sh <글번호>
# 정상 배치는 발행글 기준 H2>P>FIGURE>P (제목 → 원출처 → 그림). 2026-09-07 198~207 대조로 확인.
set -u
A="$HOME/.claude/tools/screen/aside.sh"
ID="${1:?글번호}"
TAB="~.*newpost/${ID}"
LOCK=/tmp/tistory-editor.lock

for i in $(seq 1 60); do
  mkdir "$LOCK" 2>/dev/null && break
  [ -n "$(find "$LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ] && { rmdir "$LOCK" 2>/dev/null || true; continue; }
  sleep 20
done
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

echo "▶ /$ID 위치 수정"
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

before=$("$A" eval "$TAB" '(()=>[...tinymce.activeEditor.getBody().children].slice(0,4).map(e=>e.tagName).join(">"))()' 2>/dev/null | tr -d '"')
echo "  · 수정 전: $before"

# ⚠️ 생 DOM 이동 + setDirty 만으로는 저장에 반영되지 않는다(2026-09-07 실측: 편집기엔 H2>FIGURE 로
#    보이는데 발행글은 옛 배치 그대로였다). 티스토리 저장은 **에디터 내부 모델**을 직렬화하므로
#    반드시 `undoManager.transact()` 안에서 옮기고 `ed.save()` 로 모델을 밀어넣어야 한다.
moved=$("$A" eval "$TAB" '(()=>{const ed=tinymce.activeEditor;let r="요소없음";ed.undoManager.transact(()=>{const b=ed.getBody();const f=b.querySelector("figure[data-ke-type=image]");const h=b.querySelector("h2");if(!f||!h)return;h.parentNode.insertBefore(f,h.nextSibling);r=[...b.children].slice(0,4).map(e=>e.tagName).join(">")});ed.setDirty(true);ed.fire("change");if(ed.save)ed.save();return r})()' 2>/dev/null | tr -d '"')
echo "  · 수정 후(편집기): $moved"
case "$moved" in H2\>FIGURE*) ;; *) echo "  ✗ 배치 실패 ($moved)"; exit 1;; esac

when=$("$A" eval "$TAB" '(async()=>{[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="완료").click();await new Promise(r=>setTimeout(r,3000));const d=[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim()));return (d?d.textContent.trim():"?")+" "+((document.getElementById("dateHour")||{}).value||"")+":"+((document.getElementById("dateMinute")||{}).value||"")})()' 2>/dev/null | tr -d '"')
echo "  · 예약 유지: $when"
"$A" eval "$TAB" '(async()=>{const b=[...document.querySelectorAll("button")].find(x=>/발행|저장/.test(x.textContent)&&!/임시/.test(x.textContent));b.click();await new Promise(r=>setTimeout(r,4000));return 1})()' >/dev/null 2>&1 || true

# CAPTCHA 는 사람 몫 — 프레임까지 뒤져서 판정한다
said=0
for i in $(seq 1 72); do
  sleep 5
  cap=$(bash "$(dirname "$0")/captcha_check.sh" "$ID" 2>/dev/null)
  [ "$cap" = "notab" ] && break
  if [ "$cap" = "y" ]; then
    [ "$said" = "0" ] && { echo "  ⏸ CAPTCHA — 사람이 풀 때까지 대기"; said=1; }
    continue
  fi
  [ "$said" = "1" ] && { echo "  ▶ CAPTCHA 해결됨"; sleep 6; break; }
done
echo "  (발행글 확인은 호출한 쪽에서)"
