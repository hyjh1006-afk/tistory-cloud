#!/bin/bash
# 이미 올린 예약글의 발행일시만 바꾼다.
# 사용: scripts/cedar_reschedule.sh <글번호> <YYYY-MM-DD> [시] [분]
set -euo pipefail

A="$HOME/.claude/tools/screen/aside.sh"
ID="${1:?글번호}"
WANT_DATE="${2:?YYYY-MM-DD}"
HOUR="${3:-21}"
MIN="${4:-00}"
WANT_YM="${WANT_DATE%-*}"
DAY=$(echo "${WANT_DATE##*-}" | sed 's/^0//')
TAB="~/manage/newpost/${ID}(\?.*)?$"

echo "▶ /$ID → $WANT_DATE $HOUR:$MIN"

LOCK="/tmp/tistory-editor.lock"
for i in $(seq 1 60); do
  mkdir "$LOCK" 2>/dev/null && break
  [ -n "$(find "$LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ] && { rmdir "$LOCK" 2>/dev/null || true; continue; }
  sleep 20
done
trap 'rm -rf "$LOCK"' EXIT

"$A" close "/manage/newpost/${ID}" >/dev/null 2>&1 || true
sleep 1
"$A" open "https://tester188.tistory.com/manage/post/${ID}" >/dev/null
sleep 10
ready=$("$A" eval "$TAB" '(()=>(!!document.querySelector("#post-title-inp")&&typeof window.tinymce==="object"))()')
[ "$ready" = "true" ] || { echo "  ✗ 편집기가 안 떴습니다 ($ready)"; exit 1; }

step=$("$A" eval "$TAB" '(async()=>{
[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="완료").click();
await new Promise(r=>setTimeout(r,2500));
if(!document.getElementById("open20")) return {오류:"발행창 안 뜸"};
[...document.querySelectorAll("button,a,span,label")].find(e=>e.textContent.trim()==="예약").click();
await new Promise(r=>setTimeout(r,1200));
const db=[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim()));
const vis=e=>e&&e.offsetHeight>0;
let cal=document.querySelector(".box_calendar");
if(!vis(cal)){ db.click(); await new Promise(r=>setTimeout(r,1000)); cal=document.querySelector(".box_calendar"); }
const want="'"$WANT_YM"'";
for(let i=0;i<14;i++){
  const [y,m]=cal.querySelector(".txt_calendar").textContent.replace(/[^0-9]+/g,"-").replace(/^-|-$/g,"").split("-");
  if(y+"-"+String(m).padStart(2,"0")===want) break;
  const nx=cal.querySelector(".btn_next");
  if(!nx||nx.disabled) return {오류:"달력 이동 실패"};
  nx.click(); await new Promise(r=>setTimeout(r,500));
  cal=document.querySelector(".box_calendar");
}
const day=[...cal.querySelectorAll("button.btn_day")].filter(b=>!b.disabled).find(b=>b.textContent.trim()==="'"$DAY"'");
if(!day) return {오류:"날짜 버튼 없음"};
day.click();
await new Promise(r=>setTimeout(r,900));
const h=document.getElementById("dateHour"); h.focus(); h.select();
return {날짜:[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim())).textContent.trim()};
})()')
echo "  1) $step"
case "$step" in *오류*) echo "  ✗ 예약 설정 실패"; exit 1;; esac

"$A" type "$TAB" "$HOUR" >/dev/null
"$A" eval "$TAB" '(()=>{const m=document.getElementById("dateMinute");m.focus();m.select();return 1;})()' >/dev/null
"$A" type "$TAB" "$MIN" >/dev/null
when=$("$A" eval "$TAB" '(()=>({날짜:[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim())).textContent.trim(),시:document.getElementById("dateHour").value,분:document.getElementById("dateMinute").value,공개:document.getElementById("open20").checked}))()')
echo "  2) $when"
case "$when" in *"\"$WANT_DATE\""*) ;; *) echo "  ✗ 날짜 불일치 — 중단"; exit 1;; esac
case "$when" in *"\"시\": \"$HOUR\""*) ;; *) echo "  ✗ 시각 불일치 — 중단"; exit 1;; esac
case "$when" in *"\"분\": \"$MIN\""*) ;; *) echo "  ✗ 분 불일치 — 중단"; exit 1;; esac

"$A" eval "$TAB" '(async()=>{const b=[...document.querySelectorAll("button")].find(x=>/발행|저장/.test(x.textContent)&&!/임시/.test(x.textContent));b.click();await new Promise(r=>setTimeout(r,5000));return 1;})()' >/dev/null 2>&1 || true
sleep 3
echo "  ✓ 완료"
