#!/bin/bash
# 여시 주간 연재 — 매주 월요일 예약 작업(yeosi-weekly-serial)이 부른다. 다음 편 하나를 카페에 올린다(토큰 0).
#   순서 고르기: yeosi_next.py · 실제 게시: cafe_promo.sh <글번호> (티스토리 글을 그대로 복사)
# 종료코드: 0 올림(또는 이미 있어서 기록만) · 3 연재 끝(올릴 편 없음) · 4 카페 로그인 풀림(루틴이 카카오 로그인 뒤 다시 부름)
#           5 올렸는지 확인 못 함(다시 돌리지 말고 게시판 확인) · 1 그 밖의 실패
# 2026-11-21 대표님 지시로 자동화 버튼 「03 다음카페 괴담 홍보」를 없애고 이 루틴으로 바꿨다.
set -u
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
A="$HOME/.claude/tools/screen/aside.sh"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$ROOT" || exit 1

NEXT="$(python3 scripts/yeosi_next.py)"
case "$NEXT" in
  DONE) echo "연재 끝 — 올릴 편이 없습니다"; exit 3;;
  NEXT*) ;;
  *) echo "✗ 다음 편을 못 골랐습니다: $NEXT"; exit 1;;
esac
PID="$(printf '%s' "$NEXT" | cut -f2)"; TITLE="$(printf '%s' "$NEXT" | cut -f3)"
# 시험: YEOSI_CHECK_TITLE="<제목>" 이면 그 제목으로 로그인·중복 확인만 하고 끝(카페에 안 올림)
[ -n "${YEOSI_CHECK_TITLE:-}" ] && TITLE="$YEOSI_CHECK_TITLE"
KEY="$(printf '%s' "$TITLE" | python3 -c 'import sys;print(sys.stdin.read().strip()[:22])')"
echo "▶ 이번 주 편: /$PID $TITLE"

# 1) 카페 로그인·중복 확인 (검색은 등록 확인용이 아니라 「이미 올렸나」 용 — 색인이 늦을 수 있어 확인은 아래 목록으로 한다)
CHK="$(aside repl "
const p = await openTab('https://cafe.daum.net/subdued20club/RaxJ');
await sleep(5000);
// 로그인 상태는 화면 맨 위 줄(카페 iframe)의 「로그인/로그아웃」 글자로 본다 — 페이지 소스의 「로그아웃」 문자열은 로그아웃 상태에도 들어 있다(11/21 오판)
const topLinks = async () => { let a = []; for (const f of p.frames()) { try { a = a.concat(await f.evaluate(() => [...document.querySelectorAll('a')].map(x => (x.innerText || '').trim()))); } catch (e) {} } return a; };
let tl = await topLinks();
let loggedIn = tl.includes('로그아웃') && !tl.includes('로그인');
let loginTried = 'no';
if (!loggedIn) {
  // 대표님 11/21: 「로그인 창 뜨면 카카오로 로그인 누르고」 — 저장된 간편로그인 계정을 누른다. 비밀번호 칸이 뜨면 멈춘다.
  loginTried = 'yes';
  for (const f of p.frames()) { try { const ok = await f.evaluate(() => { const a = [...document.querySelectorAll('a')].find(x => (x.innerText || '').trim() === '로그인'); if (a) { a.click(); return true; } return false; }); if (ok) break; } catch (e) {} }
  await sleep(5000);
  if (/accounts\\.kakao\\.com/.test(p.url())) {
    const hasPw = await p.evaluate(() => !!document.querySelector('input[type=password]'));
    if (hasPw) loginTried = 'password';
    else { await p.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /@/.test(x.innerText || '')); if (b) b.click(); }); await sleep(7000); }
  }
  if (!/subdued20club/.test(p.url())) { await p.goto('https://cafe.daum.net/subdued20club/RaxJ'); await sleep(5000); }
  tl = await topLinks();
  loggedIn = tl.includes('로그아웃') && !tl.includes('로그인');
}
const r = await p.evaluate(async (key) => {
  const t = await (await fetch('https://cafe.daum.net/_c21_/bbs_list?grpid=1IHuH&fldid=RaxJ', {credentials:'include'})).text();
  const s = await (await fetch('https://cafe.daum.net/_c21_/cafesearch?grpid=1IHuH&fldid=RaxJ&pagenum=1&listnum=50&item=subject&head=&query=' + encodeURIComponent(key.replace(/^\\[Reddit\\]\\s*/, '').slice(0, 30)) + '&searchPeriod=all&sorttype=0', {credentials:'include'})).text();
  const d = new DOMParser().parseFromString(s, 'text/html');
  // 같은 제목 전체 + 대표님 닉네임 + 2026-09 이후 글만 — 옛날(2022 등)에 올린 원본 편과 헷갈리지 않게
  const recent = x => { const m = x.match(/(\\d{2})\\.(\\d{2})\\.(\\d{2})/); return !m || (2000 + +m[1]) * 100 + +m[2] >= 202609; };
  const hits = [...d.querySelectorAll('tr')].map(e => e.innerText.replace(/\\s+/g, ' ')).filter(x => x.includes(key) && /연꽃이사는집/.test(x) && recent(x));
  return {write: /article-write-btn/.test(t), dup: hits.length};
}, $(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$TITLE"));
console.log('CHK=' + JSON.stringify(Object.assign({login: loggedIn, loginTried}, r)));
try { await closeTab(p); } catch (e) {}
" 2>&1 | grep '^CHK=' | sed 's/^CHK=//')"
echo "  확인: ${CHK:-응답 없음}"
case "$CHK" in
  *'"login":false'*) echo "✗ 카페 로그인이 안 됩니다(카카오 간편로그인 시도: $(printf '%s' "$CHK" | grep -o '"loginTried":"[a-z]*"')) — 비밀번호가 필요하면 대표님께"; exit 4;;
  *'"login":true'*) ;;
  *) echo "✗ Aside 로 카페 상태를 못 읽었습니다"; exit 1;;
esac
[ -n "${YEOSI_CHECK_TITLE:-}" ] && { echo "  (시험 — 확인만 하고 끝)"; exit 0; }
if printf '%s' "$CHK" | grep -q '"dup":[1-9]'; then
  echo "  · 이미 카페에 같은 제목이 있음 → 다시 올리지 않고 기록만"
  python3 scripts/yeosi_next.py --done "$PID" >/dev/null
  exit 0
fi

# 2) 게시 (cafe_promo.sh 는 실패해도 0 을 낸다 — 결과는 출력으로 판정: 완료 화면 + 게시판 목록 맨 위 3줄에 제목 앞 22자)
OUT="$(mktemp)"
bash scripts/cafe_promo.sh "$PID" 2>&1 | tee "$OUT"
RC=5
if grep -q "완료화면: true" "$OUT" && grep "8)" "$OUT" | grep -qF "$KEY"; then RC=0; fi
rm -f "$OUT"
# 3) 뒷정리 — 카페 탭은 닫는다(대표님 11/20 「띄운 탭은 닫아야」)
for _ in 1 2 3; do "$A" closeend "subdued20club/RaxJ" >/dev/null 2>&1; "$A" closeend "subdued20club" >/dev/null 2>&1; done
if [ "$RC" = 0 ]; then
  python3 scripts/yeosi_next.py --done "$PID" >/dev/null
  echo "POSTED	/$PID	$TITLE"
else
  echo "✗ 게시판 목록에서 확인이 안 됐습니다 — 다시 돌리지 말고 게시판을 직접 확인할 것"
fi
exit "$RC"
