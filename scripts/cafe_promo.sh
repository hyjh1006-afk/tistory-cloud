#!/usr/bin/env bash
# 다음카페 여시(＊여성시대＊) 홍콩할매의 속삭임 게시판에 티스토리 글을 홍보 게시한다.
#   사용법: cafe_promo.sh <티스토리 글번호>      예) cafe_promo.sh 145  ← 발행글에서 본문을 긁어온다
#           cafe_promo.sh <cedar파일명>          예) cafe_promo.sh ep1  ← 원고에서 만든다
#           cafe_promo.sh <cedar파일명> <글번호>   (postmap 에 없을 때)
#   글번호 모드는 본문 뒤의 「해설」(H2) 섹션부터는 잘라낸다 — 블로그용 요약이라 카페엔 안 넣는다.
#
# 형식(2026-09-06 사용자 기존 글에서 확인):
#   게시판=홍콩할매의 속삭임 / 말머리=소설 / 제목=티스토리 제목 그대로
#   본문 = [카페 기본 배너] + "출처 : <티스토리링크>" + 링크미리보기카드 + 본문 전문
#   등록설정 = 스크랩 허용 O, 복사 허용 X
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
A=~/.claude/tools/screen/aside.sh
TAB='~subdued20club$'
BLOG="https://tester188.tistory.com"
LOCK=/tmp/daum-cafe-editor.lock
ARG="$1"
W="${TMPDIR:-/tmp}/cafepromo.$$"; mkdir -p "$W"
export PATH="$HOME/.local/bin:$PATH"

if printf '%s' "$ARG" | grep -qE '^[0-9]+$'; then
  # ── 글번호 모드: 발행된 티스토리 글에서 제목·본문을 그대로 긁어온다 ──
  PID="$ARG"; URL="$BLOG/$PID"
  for _ in 1 2 3; do ~/.claude/tools/screen/aside.sh closeend "tistory.com/$PID" >/dev/null 2>&1; done
  ~/.claude/tools/screen/aside.sh open "$URL" >/dev/null 2>&1
  sleep 8
  aside repl "
const t=(await listBrowserTabs()).find(x=>x.url.replace(/[?#].*/,'').endsWith('/$PID'));
const p=await attachBrowserTab(t.targetId);
const d=await p.evaluate(()=>{
  const c=document.querySelector('.entry-content, .tt_article_useless_p_margin');
  const kids=[...c.children];
  let title=null, stop=kids.length;
  kids.forEach((e,i)=>{
    const tx=(e.innerText||'').trim();
    if(e.tagName==='H2'){ if(title===null) title=tx; else if(stop===kids.length) stop=i; }
  });
  const raw=[];
  kids.slice(0,stop).forEach(e=>{
    if(e.tagName==='H2') return;
    (e.innerText||'').replace(/\u00a0/g,' ').split('\n').forEach(l=>{ l=l.trim(); if(l) raw.push(l); });
  });
  // 해설은 카페에 넣지 않는다(사용자 확정 2026-09-06).
  // 두 번째 H2 로 오는 글도 있고, 본문 안에 '[해설]' 한 줄로 들어오는 글도 있다.
  // 후자는 그 줄부터 다음 '원문 링크:' 전까지를 버린다.
  const lines=[];
  let skip=false;
  raw.forEach(l=>{
    if(/^\[?\s*해설\s*\]?$/.test(l)){ skip=true; return; }
    if(skip){ if(/^원문 링크\s*:/.test(l)) skip=false; else return; }
    lines.push(l);
  });
  return {title, lines};
});
console.log('@@JSON@@'+JSON.stringify(d));
" 2>/dev/null | grep '^@@JSON@@' | sed 's/^@@JSON@@//' > "$W/post.json"
  [ -s "$W/post.json" ] || { echo "✗ 발행글에서 본문을 못 읽었다: $URL"; rm -rf "$W"; exit 1; }
  python3 -c "
import json,sys
d=json.load(open('$W/post.json',encoding='utf-8'))
open('$W/title.txt','w',encoding='utf-8').write(d['title'] or '')
open('$W/body.txt','w',encoding='utf-8').write('\n'.join(d['lines']))
"
  TITLE="$(cat "$W/title.txt")"
else
  # ── 원고 모드: cedar/<이름>.txt + postmap 에서 글번호 ──
  SRC="${ARG%.txt}"
  F="$ROOT/cedar/$SRC.txt"
  [ -f "$F" ] || { echo "✗ 원고 없음: $F"; rm -rf "$W"; exit 1; }
  TITLE="$(sed -n '1p' "$F")"
  PID="${2:-$(awk -F'\t' -v t="$TITLE" '$2==t{print $1; exit}' "$ROOT/state/postmap.txt")}"
  [ -n "${PID:-}" ] || { echo "✗ postmap 에서 글번호를 못 찾음: $TITLE"; rm -rf "$W"; exit 1; }
  URL="$BLOG/$PID"
  tail -n +3 "$F" | awk 'NF{f=1} f' > "$W/body.txt"
fi
[ -n "$TITLE" ] || { echo "✗ 제목이 비었다"; rm -rf "$W"; exit 1; }
echo "▶ $TITLE"
echo "  출처: $URL"

# ── 편집기 잠금 (카페도 임시저장 슬롯이 하나다) ──────────────────
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +20 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null
  else echo "✗ 다른 세션이 카페 편집기 사용 중 ($LOCK)"; exit 1; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT


# ── 1) 좀비 탭 정리 후 게시판 열기 → 글쓰기 ──────────────────────
for _ in 1 2 3; do "$A" closeend "subdued20club" >/dev/null 2>&1; done
sleep 1
"$A" open "https://cafe.daum.net/subdued20club/RaxJ" >/dev/null 2>&1
sleep 9
aside repl "
const t = (await listBrowserTabs()).find(x=>/subdued20club\/RaxJ\$/.test(x.url));
const p = await attachBrowserTab(t.targetId);
p.on('dialog', d=>d.dismiss());
let fl=null; for(let i=0;i<8;i++){ fl=p.frames().find(f=>/bbs_list/.test(f.url())); if(fl)break; await sleep(2000);}
await fl.evaluate(()=>document.querySelector('#article-write-btn').click());
await sleep(8000);
const fw = p.frames().find(f=>/united_write/.test(f.url()));
console.log('editor:', !!fw);
// 말머리 = 소설
await fw.evaluate(()=>[...document.querySelectorAll('a.link_item')].find(a=>/말머리/.test(a.innerText)).click());
await sleep(1200);
await fw.evaluate(()=>{
  const box=[...document.querySelectorAll('.box_opt')].find(b=>/소설/.test(b.innerText));
  [...box.querySelectorAll('a.link_menu')].find(a=>a.innerText.trim()==='소설').click();
});
await sleep(1000);
const cur = await fw.evaluate(()=>{ const o=[...document.querySelectorAll('a.link_item')].find(a=>/리스트 열기/.test(a.innerText)&&!/속삭임/.test(a.innerText)); return o?o.innerText.trim():'?'; });
console.log('말머리:', cur);
await fw.evaluate(()=>{ const i=document.querySelector('.title__input'); i.focus(); i.click(); });
" 2>&1 | sed 's/^/  /'

# ── 2) 제목 (진짜 키보드 입력) ───────────────────────────────────
"$A" type "$TAB" "$TITLE" >/dev/null 2>&1
sleep 1

# ── 3) 출처 링크 + 엔터 → 링크 미리보기 카드 ────────────────────
aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
const fw=p.frames().find(f=>/united_write/.test(f.url()));
await fw.evaluate(()=>{
  const ifr=document.querySelector('#keditorContainer_ifr'), d=ifr.contentDocument, w=ifr.contentWindow;
  w.focus();
  const last=d.body.lastElementChild, r=d.createRange();
  r.selectNodeContents(last); r.collapse(false);
  const s=w.getSelection(); s.removeAllRanges(); s.addRange(r);
});
" >/dev/null 2>&1
"$A" type "$TAB" "출처 : $URL" >/dev/null 2>&1
sleep 1
"$A" key "$TAB" Enter >/dev/null 2>&1

OG=0
for _ in 1 2 3 4 5 6 7 8; do
  sleep 3
  n=$(aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
const fw=p.frames().find(f=>/united_write/.test(f.url()));
console.log(await fw.evaluate(()=>String(document.querySelector('#keditorContainer_ifr').contentDocument.body.querySelectorAll('figure[data-ke-type=opengraph]').length)));
" 2>/dev/null | head -1 | tr -dc '0-9')
  [ "${n:-0}" != "0" ] && { OG=1; break; }
done
[ "$OG" = "1" ] && echo "  3) 링크 미리보기 카드 생성됨" || echo "  ⚠ 미리보기 카드가 안 떴다"

# ── 4) 템플릿의 "출처 : " 와 중복되면 정리 ───────────────────────
aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
const fw=p.frames().find(f=>/united_write/.test(f.url()));
await fw.evaluate(()=>{
  const d=document.querySelector('#keditorContainer_ifr').contentDocument;
  const wk=d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT); let n;
  while((n=wk.nextNode())) if(/출처\s*:\s*출처\s*:/.test(n.nodeValue)) n.nodeValue=n.nodeValue.replace(/(출처\s*:\s*)+/,'출처 : ');
});
" >/dev/null 2>&1

# ── 5) 본문 붙여넣기 (합성 paste — setContent 는 안 먹는다) ──────
python3 - "$W" <<'PY'
import json,sys,re
W=sys.argv[1]
raw=open(f"{W}/body.txt",encoding="utf-8").read().strip("\n")
esc=lambda s:s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
# 여시 스타일(2026-09-06 사용자 수정본에서 확인):
#   원고의 **줄 하나 = <p> 하나**, 그 사이마다 빈 <p>&nbsp;</p> 를 넣는다.
#   <br> 로 이으면 그 자리만 줄이 붙어버린다. 문단 전환의 추가 빈 줄은 넣지 않는다.
lines=[l.strip() for l in raw.split("\n") if l.strip()]
html="<p>&nbsp;</p>".join("<p>"+esc(l)+"</p>" for l in lines)
open(f"{W}/paste.js","w",encoding="utf-8").write("""
const t=(await listBrowserTabs()).find(x=>/subdued20club$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
const fw=p.frames().find(f=>/united_write/.test(f.url()));
await fw.evaluate((html)=>{
  const ifr=document.querySelector('#keditorContainer_ifr'), d=ifr.contentDocument, w=ifr.contentWindow;
  w.focus();
  const last=d.body.lastElementChild, r=d.createRange();
  r.selectNodeContents(last); r.collapse(false);
  const s=w.getSelection(); s.removeAllRanges(); s.addRange(r);
  const dt=new DataTransfer();
  dt.setData('text/html', html);
  dt.setData('text/plain', html.replace(/<[^>]+>/g,''));
  (d.activeElement||d.body).dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:dt}));
}, %s);
await sleep(3000);
const c=await fw.evaluate(()=>{const d=document.querySelector('#keditorContainer_ifr').contentDocument;return d.body.children.length+'개 블록 / '+d.body.innerText.length+'자';});
console.log('본문:', c);
""" % json.dumps(html, ensure_ascii=False))
PY
aside repl "$(cat "$W/paste.js")" 2>&1 | grep -E '본문:' | sed 's/^/  5) /'

# ── 6) 등록설정: 스크랩 허용 O / 복사 허용 X ─────────────────────
aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
const fw=p.frames().find(f=>/united_write/.test(f.url()));
await fw.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(e=>/btn_edit/.test((e.className||'').toString())); if(b)b.click();});
await sleep(1500);
const st=await fw.evaluate(()=>{
  const bx=[...document.querySelectorAll('input[type=checkbox]')];
  const sc=bx.find(e=>/스크랩/.test(e.parentElement.innerText||''));
  const cp=bx.find(e=>/복사/.test(e.parentElement.innerText||''));
  if(sc && !sc.checked) sc.click();
  if(cp && cp.checked) cp.click();
  const done=[...document.querySelectorAll('button,a')].find(e=>(e.innerText||'').trim()==='완료'); if(done)done.click();
  return bx.map(e=>(e.parentElement.innerText||'').trim().slice(0,6)+'='+e.checked).join(' ');
});
console.log('설정:', st);
" 2>&1 | grep -E '설정:' | sed 's/^/  6) /'

# ── 7) 등록 ──────────────────────────────────────────────────────
aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
p.on('dialog', d=>{ console.log('DIALOG:', d.message()); d.accept(); });
const fw=p.frames().find(f=>/united_write/.test(f.url()));
const r=await fw.evaluate(()=>{
  const b=[...document.querySelectorAll('button')].find(e=>(e.innerText||'').trim()==='등록' && /full_type1/.test((e.className||'').toString()));
  if(!b) return 'no button'; b.click(); return 'clicked';
});
console.log('등록:', r);
await sleep(9000);
console.log('완료화면:', p.frames().some(f=>/post_article|bbs_done/.test(f.url())));
" 2>&1 | grep -E '등록:|완료화면:|DIALOG:' | sed 's/^/  7) /'

# ── 8) 목록에서 직접 확인 (검색으로 확인하지 말 것) ──────────────
for _ in 1 2 3; do "$A" closeend "subdued20club" >/dev/null 2>&1; done
sleep 1
"$A" open "https://cafe.daum.net/subdued20club/RaxJ" >/dev/null 2>&1
sleep 10
aside repl "
const t=(await listBrowserTabs()).find(x=>/subdued20club\/RaxJ\$/.test(x.url));
const p=await attachBrowserTab(t.targetId);
let fl=null; for(let i=0;i<8;i++){ fl=p.frames().find(f=>/bbs_list/.test(f.url())); if(fl)break; await sleep(2000);}
const rows=await fl.evaluate(()=>[...document.querySelectorAll('tr')].map(tr=>tr.innerText.replace(/\s+/g,' ').trim()).filter(r=>/^\d{6}/.test(r)).slice(0,3));
rows.forEach(r=>console.log('  ', r.slice(0,100)));
" 2>&1 | grep -v '^\[' | sed 's/^/  8) /'
rm -rf "$W"
echo "완료."
