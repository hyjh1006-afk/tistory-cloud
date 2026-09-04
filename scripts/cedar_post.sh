#!/bin/bash
# 시더빌 리마스터 1편을 티스토리에 예약 발행한다 (Aside CDP).
# 사용: scripts/cedar_post.sh <epN> <예약일(1~31)> [시] [분]
#   예: scripts/cedar_post.sh ep1 5 21 00
set -euo pipefail

A="$HOME/.claude/tools/screen/aside.sh"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
EP="${1:?epN 을 넘기세요}"
DAY="${2:?예약일(1~31)을 넘기세요}"
HOUR="${3:-21}"
MIN="${4:-00}"
RAW="https://raw.githubusercontent.com/hyjh1006-afk/tistory-cloud/main/state/outputs/cedar_${EP}.json"
TITLE="$("$ROOT/.venv/bin/python" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['title'])" "$ROOT/state/local_outputs/cedar_${EP}.json")"

echo "▶ $EP : $TITLE"
echo "  예약 → ${DAY}일 ${HOUR}:${MIN}"

# 0) 편집기 준비. 얼어붙은 탭이 있으면 닫고 새로 연다.
"$A" close "manage/newpost" >/dev/null 2>&1 || true
sleep 1
"$A" open "https://tester188.tistory.com/manage/newpost/" >/dev/null
sleep 10
ready=$("$A" eval "manage/newpost" '(()=>(!!document.querySelector("#post-title-inp") && typeof window.tinymce==="object"))()')
[ "$ready" = "true" ] || { echo "  ✗ 편집기가 안 떴습니다 ($ready)"; exit 1; }

# 1) 카테고리(이름으로) + 본문 붙여넣기 + 제목칸 포커스
step1=$("$A" eval "manage/newpost" '(async()=>{
document.querySelector("#category-btn").click();
await new Promise(r=>setTimeout(r,600));
const c=[...document.querySelectorAll("#category-list li, #category-list [role=option]")].find(e=>/시더빌/.test(e.textContent));
if(!c) return {오류:"카테고리 없음"};
c.click();
await new Promise(r=>setTimeout(r,400));
const d=await (await fetch("'"$RAW"'",{cache:"no-store"})).json();
const ed=window.tinymce.get("editor-tistory");
ed.focus(); ed.selection.select(ed.getBody(), true);
const dt=new DataTransfer();
dt.setData("text/html", d.html);
dt.setData("text/plain", d.html.replace(/<[^>]+>/g,""));
ed.getBody().dispatchEvent(new ClipboardEvent("paste",{clipboardData:dt,bubbles:true,cancelable:true}));
await new Promise(r=>setTimeout(r,1200));
document.querySelector("#post-title-inp").focus();
return {본문:ed.getContent().length, 카테고리:document.querySelector("#category-btn").textContent.trim(), 활성:document.activeElement.id};
})()')
echo "  1) $step1"
case "$step1" in *시더빌*) ;; *) echo "  ✗ 카테고리 실패"; exit 1;; esac

# 2) 제목은 진짜 입력으로 (JS 대입은 발행 때 지워진다)
"$A" type "manage/newpost" "$TITLE" >/dev/null
title_now=$("$A" eval "manage/newpost" '(()=>document.querySelector("#post-title-inp").value)()')
[ "$title_now" != '""' ] || { echo "  ✗ 제목 입력 실패"; exit 1; }

# 3) 완료 → 예약 → 날짜·시각
step3=$("$A" eval "manage/newpost" '(async()=>{
[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="완료").click();
await new Promise(r=>setTimeout(r,2200));
if(!document.getElementById("open20")) return {오류:"발행창 안 뜸"};
const res=[...document.querySelectorAll("button,a,span,label")].find(e=>e.textContent.trim()==="예약");
res.click();
await new Promise(r=>setTimeout(r,1200));
let db=[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim()));
const vis=e=>e&&e.offsetHeight>0;
let cal=document.querySelector(".box_calendar");
if(!vis(cal)){ db.click(); await new Promise(r=>setTimeout(r,1000)); cal=document.querySelector(".box_calendar"); }
const day=[...cal.querySelectorAll("button.btn_day")].find(b=>b.textContent.trim()==="'"$DAY"'");
if(!day) return {오류:"날짜 버튼 없음"};
day.click();
await new Promise(r=>setTimeout(r,900));
const h=document.getElementById("dateHour"); h.focus(); h.select();
return {날짜:[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim())).textContent.trim()};
})()')
echo "  3) $step3"
case "$step3" in *오류*) echo "  ✗ 예약 설정 실패"; exit 1;; esac

"$A" type "manage/newpost" "$HOUR" >/dev/null
"$A" eval "manage/newpost" '(()=>{const m=document.getElementById("dateMinute");m.focus();m.select();return 1;})()' >/dev/null
"$A" type "manage/newpost" "$MIN" >/dev/null
when=$("$A" eval "manage/newpost" '(()=>({날짜:[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim())).textContent.trim(),시:document.getElementById("dateHour").value,분:document.getElementById("dateMinute").value,공개:document.getElementById("open20").checked}))()')
echo "  4) $when"

# 4) 발행
"$A" eval "manage/newpost" '(async()=>{const b=[...document.querySelectorAll("button")].find(x=>/발행|저장/.test(x.textContent)&&!/임시/.test(x.textContent));b.click();await new Promise(r=>setTimeout(r,5000));return 1;})()' >/dev/null 2>&1 || true
sleep 3
echo "  ✓ 발행 요청 완료"
