#!/bin/bash
# 시더빌 리마스터 1편을 티스토리에 예약 발행한다 (Aside CDP).
# 사용: scripts/cedar_post.sh <epN> <예약일(1~31)> [시] [분]
#   예: scripts/cedar_post.sh ep1 5 21 00
set -euo pipefail

A="$HOME/.claude/tools/screen/aside.sh"
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
EP="${1:?epN 을 넘기세요}"
CAT="${CEDAR_CAT:-시더빌}"   # 카테고리 이름 조각 (환경변수로 바꿀 수 있음)
TAB='~/manage/newpost/(\?.*)?$'
DAY="${2:?예약일(1~31)을 넘기세요}"
HOUR="${3:-21}"
MIN="${4:-00}"
RAW="https://raw.githubusercontent.com/hyjh1006-afk/tistory-cloud/main/state/outputs/cedar_${EP}.json"
TITLE="$("$ROOT/.venv/bin/python" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['title'])" "$ROOT/state/local_outputs/cedar_${EP}.json")"

# 기대 예약일. 날짜는 YYYY-MM-DD 로 넘기는 걸 권장한다.
# 숫자만 넘기면 "다음에 오는 그 날"로 해석한다 — 오늘과 같은 날짜를 넘기면
# 이번 달 오늘이 되어 몇 시간 뒤 공개돼버린다(2026-09-04에 당함). 헷갈리면 전체 날짜를 써라.
WANT_DATE="$(/usr/bin/python3 - "$DAY" <<'PY'
import sys, datetime, re
a = sys.argv[1]
if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a):
    print(a)
else:
    d = int(a); t = datetime.date.today()
    y, m = (t.year, t.month) if d > t.day else (t.year + (t.month == 12), t.month % 12 + 1)
    print(f"{y:04d}-{m:02d}-{d:02d}")
PY
)"

WANT_YM="${WANT_DATE%-*}"
DAY="$(echo "${WANT_DATE##*-}" | sed 's/^0//')"

echo "▶ $EP : $TITLE"
echo "  예약 → ${WANT_DATE} ${HOUR}:${MIN}"

# ── 편집기 잠금. 티스토리 임시저장 슬롯은 블로그당 하나뿐이라
#    매일 18:26 괴담 루틴과 겹치면 서로 제목·본문을 덮어쓴다 (2026-09-04 실측).
#    매일 괴담 루틴은 18:26 에 시작한다. 그 창은 아예 피한다(루틴 쪽은 잠금을 안 본다).
now_hm=$(date +%H%M)
if [ "${CEDAR_FORCE:-0}" != "1" ] && [ "$now_hm" -ge 1820 ] && [ "$now_hm" -le 1855 ]; then
  echo "  ✗ 18:20~18:55 는 매일 괴담 루틴 시간대입니다 — 나중에 실행하세요"; exit 1
fi
LOCK="/tmp/tistory-editor.lock"
for i in $(seq 1 60); do
  if mkdir "$LOCK" 2>/dev/null; then break; fi
  # 20분 넘게 남아 있으면 죽은 잠금으로 보고 뺏는다
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null || true; continue; fi
  [ "$i" = 1 ] && echo "  … 다른 세션이 편집기 사용 중. 대기"
  sleep 20
done
[ -d "$LOCK" ] || { echo "  ✗ 편집기 잠금 실패"; exit 1; }
echo "$$ cedar_post $EP" > "$LOCK/owner" 2>/dev/null || true
trap 'rm -rf "$LOCK"' EXIT

# 0) 편집기 준비. 내 새 글 탭만 닫고 새로 연다.
# ⚠️ close "manage/newpost" 는 남의 편집 탭(/manage/newpost/147 등)까지 닫는다 — closeend 로 정확히 끝나는 것만.
"$A" closeend "/manage/newpost/" >/dev/null 2>&1 || true
"$A" closeend "/manage/newpost/?type=post" >/dev/null 2>&1 || true
sleep 1
"$A" open "https://tester188.tistory.com/manage/newpost/" >/dev/null
sleep 10
READY_JS='(()=>(!!document.querySelector("#post-title-inp") && typeof window.tinymce==="object"))()'
ready=$("$A" eval "$TAB" "$READY_JS" 2>/dev/null || echo timeout)
if [ "$ready" != "true" ]; then
  # Aside 는 WebKit 계열이라 네이티브 confirm 을 CDP 로 못 닫는다.
  # "…에 저장된 글이 있습니다. 이어서 작성하시겠습니까?" 가 뜨면 렌더러가 멈춰 eval 이 타임아웃난다.
  # → 물리 클릭으로 [취소] (이어서 작성하면 남의 초안이 딸려 들어온다)
  echo "  · 편집기 무응답 — 저장된 글 확인창으로 보고 [취소] 클릭"
  "$HOME/.claude/tools/screen/aside_confirm.sh" cancel || true
  sleep 2
  ready=$("$A" eval "$TAB" "$READY_JS" 2>/dev/null || echo timeout)
fi
[ "$ready" = "true" ] || { echo "  ✗ 편집기가 안 떴습니다 ($ready)"; exit 1; }

# 1) 카테고리(이름으로) + 본문 붙여넣기 + 제목칸 포커스
step1=$("$A" eval "$TAB" '(async()=>{
document.querySelector("#category-btn").click();
await new Promise(r=>setTimeout(r,600));
const c=[...document.querySelectorAll("#category-list li, #category-list [role=option]")].find(e=>/'"$CAT"'/.test(e.textContent));
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
case "$step1" in *"$CAT"*) ;; *) echo "  ✗ 카테고리 실패"; exit 1;; esac

# 2) 제목은 진짜 입력으로 (JS 대입은 발행 때 지워진다)
"$A" type "$TAB" "$TITLE" >/dev/null
title_now=$("$A" eval "$TAB" '(()=>document.querySelector("#post-title-inp").value)()')
[ "$title_now" != '""' ] || { echo "  ✗ 제목 입력 실패"; exit 1; }

# 3) 완료 → 예약 → 날짜·시각
step3=$("$A" eval "$TAB" '(async()=>{
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
// 다음 달 이후를 예약하려면 달력을 넘겨야 한다 (안 넘기면 이번 달 같은 날짜가 찍힌다)
const want="'"$WANT_YM"'";
for(let i=0;i<14;i++){
  const h=cal.querySelector(".txt_calendar").textContent.replace(/[^0-9]+/g,"-").replace(/^-|-$/g,"");
  const [y,m]=h.split("-");
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
echo "  3) $step3"
case "$step3" in *오류*) echo "  ✗ 예약 설정 실패"; exit 1;; esac

"$A" type "$TAB" "$HOUR" >/dev/null
"$A" eval "$TAB" '(()=>{const m=document.getElementById("dateMinute");m.focus();m.select();return 1;})()' >/dev/null
"$A" type "$TAB" "$MIN" >/dev/null
when=$("$A" eval "$TAB" '(()=>({날짜:[...document.querySelectorAll("button")].find(b=>/^\d{4}-\d{2}-\d{2}$/.test(b.textContent.trim())).textContent.trim(),시:document.getElementById("dateHour").value,분:document.getElementById("dateMinute").value,공개:document.getElementById("open20").checked}))()')
echo "  4) $when"

# ⚠️ 예약값을 못 잡았는데 발행하면 "지금 공개발행" 이 된다 (2026-09-04에 한 번 당함).
#    날짜·시·분이 전부 원하는 값일 때만 발행 버튼을 누른다.
case "$when" in
  *"\"$WANT_DATE\""*) ;;
  *) echo "  ✗ 예약일이 $WANT_DATE 가 아닙니다 — 발행하지 않고 중단"; exit 1;;
esac
case "$when" in
  *"\"시\": \"$HOUR\""*) ;;
  *) echo "  ✗ 시각이 $HOUR 가 아닙니다 — 발행하지 않고 중단"; exit 1;;
esac
case "$when" in
  *"\"분\": \"$MIN\""*) ;;
  *) echo "  ✗ 분이 $MIN 이 아닙니다 — 발행하지 않고 중단"; exit 1;;
esac

# 4) 발행
"$A" eval "$TAB" '(async()=>{const b=[...document.querySelectorAll("button")].find(x=>/발행|저장/.test(x.textContent)&&!/임시/.test(x.textContent));b.click();await new Promise(r=>setTimeout(r,4000));return 1;})()' >/dev/null 2>&1 || true
sleep 4

# 5) 검증 — 발행 버튼을 눌러도 글이 안 만들어지는 경우가 있다(하루 한도 등). 반드시 확인한다.
# ⚠️ ?searchKeyword= 검색은 방금 만든 글을 못 찾아 오판하게 만든다. 목록 첫 페이지를 직접 읽을 것.
LIST="https://tester188.tistory.com/manage/posts/"
# ⚠️ 목록 탭이 여러 개 쌓이면 find() 가 오래된 좀비 탭을 잡아 검증이 **항상 false** 가 된다
#    (2026-09-05 실측: 실제로 만들어진 글도 "없음"으로 나옴). 검증 전에 싹 닫고 새로 연다.
for _ in 1 2 3 4 5 6; do "$A" closeend "tistory.com/manage/posts/" >/dev/null 2>&1 || true; done
"$A" open "$LIST" >/dev/null 2>&1 || true
sleep 7
TITLE_JS=$(/usr/bin/python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$TITLE")
found=$("$A" eval '~.*manage/posts/$' \
  "(()=>[...document.querySelectorAll('.list_post li')].some(e=>e.innerText.includes(${TITLE_JS})))()" \
  2>/dev/null || echo unknown)
if [ "$found" = "true" ]; then
  echo "  ✓ 발행 확인됨 — $WANT_DATE $HOUR:$MIN"
else
  echo "  ✗ 발행됐다는 증거가 없습니다 (목록에 제목 없음: $found)"; exit 1
fi
