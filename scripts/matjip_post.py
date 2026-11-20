# -*- coding: utf-8 -*-
"""맛집 후기 1편을 티스토리 「맛집」 카테고리에 공개 발행한다 (Aside repl). 진입점 scripts/matjip_post.sh.

입력 JSON: {"title": "...", "html": "<p>…</p><p>[[IMG1]]</p>…<p>[[PLACE]]</p>", "images": ["/abs/1.jpg", ...], "category": "맛집",
           "place": {"query": "리샨 여의도점", "match": "리샨"}}   ← place 는 선택. [[PLACE]] 자리에 툴바 「장소」 카드(카카오맵 연결)
  - 사진 자리는 본문에 <p>[[IMGn]]</p> 로 둔다(n 은 images 의 1부터). 사진은 matjip.sh export 가 만든 것(위치 정보 지운 JPEG).
  - "at": "YYYY-MM-DD HH:MM" 를 넣으면 예약 발행(publish_waiting 과 같은 방식).

사진 올리는 길(2026-11-20 실측): aside repl 은 세션 폴더 밖 파일을 못 읽고(fs·setInputFiles 둘 다), CLI 는 호출마다 세션 폴더가 바뀐다.
→ 사진을 base64 조각(40만 자)으로 나눠 편집기 페이지 window 에 쌓은 뒤, 페이지 안에서 File 로 만들어
  툴바 「첨부 → 사진」 이 만든 input[type=file] 에 DataTransfer 로 꽂고 change 를 쏜다. 올라온 figure 로 [[IMGn]] 문단을 바꾼다.

종료 코드는 publish_waiting 과 같다: 0 정상 · 1 저장 전 검사 실패(저장 안 함) · 2 Aside · 4 로그인 · 5 눌렀는데 확인 못 함(재시도 금지) · 7 캡챠 · 8 잠금
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_waiting as pw  # noqa: E402  (잠금·repl·캡챠 중계·자동저장 정리를 같이 쓴다)
from publish_waiting import Stop, OK, GATE, ASIDE_DOWN, LOGIN, UNVERIFIED, CAPTCHA, log, notify  # noqa: E402

CHUNK = 400_000


def push_image(tid: str, key: str, path: str) -> int:
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    for i in range(0, len(b64), CHUNK):
        part = b64[i:i + CHUNK]
        res, _ = pw.repl(pw.attach_js(tid) + f"""
return await P.evaluate(([k, c, first]) => {{ window.__mj = window.__mj || {{}}; window.__mj[k] = (first ? '' : (window.__mj[k] || '')) + c; return window.__mj[k].length; }}, [{json.dumps(key)}, {json.dumps(part)}, {str(i == 0).lower()}]);
""", timeout=90)
        if not isinstance(res, int):
            raise Stop(GATE, f"사진 조각 전달 실패: {res}")
    if res != len(b64):
        raise Stop(GATE, f"사진 길이 불일치 {res} != {len(b64)}")
    return len(b64)


def open_editor(tid: str, d: dict) -> dict:
    body = pw.attach_js(tid) + f"""
const D = {json.dumps(d, ensure_ascii=False)};
await P.goto({json.dumps(pw.BLOG + "/manage/newpost/")});
let ready = false;
for (let i = 0; i < 50; i++) {{
  const u = P.url();
  if (/auth\\/login|accounts\\.kakao\\.com/.test(u)) return {{login:false, href:u}};
  try {{ ready = await P.evaluate(() => !!document.querySelector('#post-title-inp') && !!(window.tinymce && tinymce.get('editor-tistory')) && !!document.querySelector('#category-btn')); }} catch (e) {{}}
  if (ready) break; await sleep(400);
}}
if (!ready) return {{error:'편집기가 안 뜸', href:P.url()}};
await sleep(2000);
const s1 = await P.evaluate(async (D) => {{
  if (!window.__pwPatched) {{
    window.__pwPatched = true; window.__pwBlocked = 0;
    const isAuto = (m, u) => String(m).toUpperCase() === 'POST' && /\\/manage\\/autosave(\\?|$)/.test(String(u));
    const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) {{ this.__pw = [m, u]; return oo.apply(this, arguments); }};
    XMLHttpRequest.prototype.send = function () {{ if (this.__pw && isAuto(this.__pw[0], this.__pw[1])) {{ window.__pwBlocked++; try {{ this.abort(); }} catch (e) {{}} return; }} return os.apply(this, arguments); }};
    const of = window.fetch; window.__pwOrigFetch = of;
    window.fetch = function (i, o) {{ const u = (i && i.url) || i, m = (o && o.method) || (i && i.method) || 'GET'; if (isAuto(m, u)) {{ window.__pwBlocked++; return Promise.reject(new Error('autosave blocked')); }} return of.apply(this, arguments); }};
  }}
  const ed = tinymce.get('editor-tistory');
  const norm = s => (s || '').replace(/\\s+/g, '');
  if (document.querySelector('#post-title-inp').value !== '' || norm(ed.getBody().textContent).length !== 0) return {{ok:false, why:'편집기가 비어 있지 않음(남의 초안?)'}};
  document.querySelector('#category-btn').click();
  await new Promise(r => setTimeout(r, 700));
  const opts = [...document.querySelectorAll('#category-list li, #category-list [role=option]')];
  const opt = opts.find(e => e.textContent.trim().replace(/^-\\s*/, '') === D.cat);
  if (!opt) return {{ok:false, why:'카테고리 항목 없음: '+D.cat}};
  opt.click();
  await new Promise(r => setTimeout(r, 500));
  ed.focus(); ed.selection.select(ed.getBody(), true);
  const dt = new DataTransfer();
  dt.setData('text/html', D.html); dt.setData('text/plain', D.html.replace(/<[^>]+>/g, ''));
  ed.getBody().dispatchEvent(new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}}));
  await new Promise(r => setTimeout(r, 1500));
  const t = document.querySelector('#post-title-inp'); t.focus(); t.setSelectionRange(0, t.value.length);
  return {{ok:true, holders: (ed.getBody().innerHTML.match(/\\[\\[IMG\\d+\\]\\]/g) || []).length}};
}}, D);
if (!s1.ok) return s1;
await P.keyboard.insertText(D.title);
await sleep(600);
return Object.assign(s1, {{title: await P.evaluate(() => document.querySelector('#post-title-inp').value)}});
"""
    return pw.repl(body)[0]


def place_image(tid: str, n: int, key: str, fname: str) -> dict:
    body = pw.attach_js(tid) + f"""
const A = {json.dumps({"tag": f"[[IMG{n}]]", "key": key, "fname": fname})};
return await P.evaluate(async (A) => {{
  const ed = tinymce.get('editor-tistory');
  const doc = ed.getBody();
  const holder = [...doc.querySelectorAll('p')].find(p => p.textContent.trim() === A.tag);
  if (!holder) return {{ok:false, why:'자리표시 없음 '+A.tag}};
  ed.focus(); ed.selection.select(holder, true); ed.selection.collapse(false);
  const before = new Set([...doc.querySelectorAll('figure img')].map(i => i.getAttribute('src')));
  const btn = [...document.querySelectorAll('.mce-btn')].find(e => e.getAttribute('aria-label') === '첨부' && e.offsetParent !== null);
  if (!btn) return {{ok:false, why:'첨부 버튼 없음'}};
  (btn.querySelector('button') || btn).click();
  await new Promise(r => setTimeout(r, 1500));
  const item = [...document.querySelectorAll('.mce-menu-item')].find(e => (e.innerText || '').trim() === '사진' && e.offsetParent !== null);
  if (!item) return {{ok:false, why:'사진 메뉴 없음'}};
  // 「사진」은 파일 입력칸을 즉석에서 만들어 click() 한다 → 그 click 을 가로채 파일 창을 안 띄우고 그 칸을 잡는다
  let caught = null;
  const origClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function () {{ if (this.type === 'file') {{ caught = this; return; }} return origClick.apply(this, arguments); }};
  try {{
    item.click();
    for (let i = 0; i < 20 && !caught; i++) await new Promise(r => setTimeout(r, 150));
  }} finally {{ HTMLInputElement.prototype.click = origClick; }}
  const inp = caught || [...document.querySelectorAll('input[type=file]')].filter(i => /^image/.test(i.accept || '')).pop();
  if (!inp) return {{ok:false, why:'파일 입력칸 없음'}};
  const bin = atob(window.__mj[A.key]);
  const u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  const dt = new DataTransfer(); dt.items.add(new File([u8], A.fname, {{type:'image/jpeg'}}));
  inp.files = dt.files;
  inp.dispatchEvent(new Event('change', {{bubbles:true}}));
  let fig = null;
  for (let i = 0; i < 60 && !fig; i++) {{
    await new Promise(r => setTimeout(r, 1000));
    fig = [...doc.querySelectorAll('figure')].find(f => {{ const im = f.querySelector('img'); return im && !before.has(im.getAttribute('src')) && /kakaocdn|daumcdn|tistory/.test(im.getAttribute('src') || ''); }});
  }}
  if (!fig) return {{ok:false, why:'업로드된 사진이 안 보임'}};
  const h2 = [...doc.querySelectorAll('p')].find(p => p.textContent.trim() === A.tag);
  if (h2) h2.replaceWith(fig);
  delete window.__mj[A.key];
  ed.setDirty(true); ed.fire('change');
  return {{ok:true, src: fig.querySelector('img').getAttribute('src').slice(0, 80), figs: doc.querySelectorAll('figure img').length}};
}}, A);
"""
    return pw.repl(body, timeout=120)[0]


def place_card(tid: str, query: str, match: str) -> dict:
    """[[PLACE]] 문단 자리에 툴바 「장소」 카드(가게 이름·주소, 카카오맵 연결)를 넣는다 — 11/20 실측: figure[data-ke-type=location]."""
    body = pw.attach_js(tid) + f"""
const A = {json.dumps({"q": query, "m": match}, ensure_ascii=False)};
const pre = await P.evaluate(() => {{
  const ed = tinymce.get('editor-tistory');
  const h = [...ed.getBody().querySelectorAll('p')].find(p => p.textContent.trim() === '[[PLACE]]');
  if (!h) return {{ok:false, why:'[[PLACE]] 자리표시 없음'}};
  ed.focus(); ed.selection.select(h, true); ed.selection.collapse(false);
  const b = [...document.querySelectorAll('.mce-btn')].find(e => e.getAttribute('aria-label') === '장소' && e.offsetParent !== null);
  if (!b) return {{ok:false, why:'장소 버튼 없음'}};
  (b.querySelector('button') || b).click();
  return {{ok:true}};
}});
if (!pre.ok) return pre;
const box = P.locator('input[placeholder="장소명을 입력해주세요."]').first();
await box.waitFor({{timeout: 8000}});
await box.fill(A.q);
await box.press('Enter');
await sleep(2500);
const items = P.locator('[role=dialog] li, .layer_location li, li').filter({{hasText: A.m}});
const n = await items.count();
if (!n) {{ const all = await P.evaluate(() => [...document.querySelectorAll('[role=dialog] li')].map(l => l.innerText.replace(/\\s+/g,' ').slice(0,60))); await P.keyboard.press('Escape'); return {{ok:false, why:'장소 검색 결과에 「'+A.m+'」 없음', all}}; }}
const picked = (await items.first().innerText()).replace(/\\s+/g, ' ').slice(0, 80);
await items.first().click();
await sleep(1500);
return await P.evaluate((picked) => {{
  const ed = tinymce.get('editor-tistory');
  const fig = ed.getBody().querySelector('figure[data-ke-type=location]');
  if (!fig) return {{ok:false, why:'장소 카드가 안 들어감'}};
  const h = [...ed.getBody().querySelectorAll('p')].find(p => p.textContent.trim() === '[[PLACE]]');
  if (h) h.replaceWith(fig);
  ed.setDirty(true); ed.fire('change');
  return {{ok:true, picked, name: fig.querySelector('.location-name')?.textContent, addr: fig.querySelector('.location-address')?.textContent}};
}}, picked);
"""
    return pw.repl(body)[0]


def open_layer(tid: str, d: dict) -> tuple[dict, list[str]]:
    """완료 → 공개 → (예약). 마지막에 게이트용 상태와 스크린샷."""
    body = pw.attach_js(tid) + f"""
const D = {json.dumps(d, ensure_ascii=False)};
const s2 = await P.evaluate(async (D) => {{
  const done = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '완료');
  if (!done) return {{ok:false, why:'완료 버튼 없음'}};
  done.click();
  let o = null;
  for (let i = 0; i < 20 && !o; i++) {{ await new Promise(r => setTimeout(r, 250)); o = document.getElementById(D.radio); }}
  if (!o) return {{ok:false, why:'발행 레이어 안 뜸'}};
  (document.querySelector('label[for=' + D.radio + ']') || o.parentElement).click();
  await new Promise(r => setTimeout(r, 800));
  if (D.at) {{
    const [wd] = D.at.split(' ');
    const wantYM = wd.slice(0, 7), wantDay = String(Number(wd.slice(8, 10)));
    const res = [...document.querySelectorAll('button,a,span,label')].find(e => e.textContent.trim() === '예약' && e.offsetParent !== null);
    if (!res) return {{ok:false, why:'예약 버튼 없음'}};
    res.click(); await new Promise(r => setTimeout(r, 1200));
    const dbtn = () => [...document.querySelectorAll('button')].find(b => /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(b.textContent.trim()));
    let cal = document.querySelector('.box_calendar');
    if (!(cal && cal.offsetHeight > 0)) {{ dbtn().click(); await new Promise(r => setTimeout(r, 1000)); cal = document.querySelector('.box_calendar'); }}
    for (let i = 0; i < 14; i++) {{
      const [y, m] = cal.querySelector('.txt_calendar').textContent.replace(/[^0-9]+/g, '-').replace(/^-|-$/g, '').split('-');
      if (y + '-' + String(m).padStart(2, '0') === wantYM) break;
      cal.querySelector('.btn_next').click(); await new Promise(r => setTimeout(r, 500)); cal = document.querySelector('.box_calendar');
    }}
    const day = [...cal.querySelectorAll('button.btn_day')].filter(b => !b.disabled).find(b => b.textContent.trim() === wantDay);
    if (!day) return {{ok:false, why:'날짜 버튼 없음'}};
    day.click(); await new Promise(r => setTimeout(r, 900));
    const h = document.getElementById('dateHour'); h.focus(); h.select();
  }}
  return {{ok:true}};
}}, D);
if (!s2.ok) return s2;
if (D.at) {{
  const [HH, MM] = D.at.split(' ')[1].split(':');
  await P.keyboard.insertText(HH); await sleep(300);
  await P.evaluate(() => {{ const m = document.getElementById('dateMinute'); m.focus(); m.select(); }});
  await P.keyboard.insertText(MM); await sleep(500);
}}
const s3 = await P.evaluate(() => {{
  const ed = tinymce.get('editor-tistory');
  const btn = document.getElementById('publish-btn');
  const db = [...document.querySelectorAll('button')].find(b => /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(b.textContent.trim()) && b.offsetParent !== null);
  const hh = document.getElementById('dateHour'), mm = document.getElementById('dateMinute');
  return {{ok:true, title: document.querySelector('#post-title-inp').value,
    cat: document.querySelector('#category-btn').textContent.replace(/더보기\\s*$/, '').trim(),
    edText: (ed.getBody().textContent || '').replace(/\\s+/g, '').length,
    figs: [...ed.getBody().querySelectorAll('figure img')].filter(i => /kakaocdn|daumcdn|tistory/.test(i.getAttribute('src') || '')).length,
    holders: (ed.getBody().innerHTML.match(/\\[\\[(IMG\\d+|PLACE)\\]\\]/g) || []).length,
    place: !!ed.getBody().querySelector('figure[data-ke-type=location]'),
    tags: ((document.querySelector('.editor_tag') || {{}}).innerText || '').replace(/#/g, '').trim(),
    open20: !!document.getElementById('open20')?.checked, open0: !!document.getElementById('open0')?.checked, open15: !!document.getElementById('open15')?.checked,
    btnText: btn ? btn.textContent.trim() : null, btnDisabled: btn ? btn.disabled : null,
    resDate: db ? db.textContent.trim() : null, resHour: hh && hh.offsetParent !== null ? hh.value : null, resMin: mm && mm.offsetParent !== null ? mm.value : null}};
}});
const shot = await P.screenshot({{type:'jpeg', quality:55}});
console.log('SHOT=' + shot.toString('base64'));
return s3;
"""
    return pw.repl(body)


def verify(tid: str, it: dict, n_img: int) -> dict:
    body = pw.attach_js(tid) + f"""
const D = {json.dumps({"title": it["title"], "cat": it["cat"]}, ensure_ascii=False)};
if (!/tester188\\.tistory\\.com\\/manage/.test(P.url())) {{ await P.goto({json.dumps(pw.BLOG + "/manage/posts/")}); await sleep(2500); }}
return await P.evaluate(async (D) => {{
  {pw.J_FN}
  let hit = null;
  for (let a = 0; a < 4 && !hit; a++) {{
    if (a) await new Promise(r => setTimeout(r, 4000));
    const r = await J('/manage/posts.json?category=-3&page=1&searchKeyword=&searchType=title&visibility=all');
    hit = ((r.j && r.j.items) || []).find(p => p.title === D.title);
  }}
  if (!hit) return {{found:false}};
  if (hit.visibility !== 'PUBLIC') return {{found:true, id:hit.id, visibility:hit.visibility, category:hit.category, published:hit.published, permalink:hit.permalink}};
  const r = await F(hit.permalink || ('/' + hit.id), {{cache:'no-store', credentials:'include'}});
  const t = await r.text();
  const view = (t.split('article_view')[1] || '');
  return {{found:true, id:hit.id, visibility:hit.visibility, category:hit.category, permalink:hit.permalink, published:hit.published,
    page:r.status, imgs:(view.match(/<img /g) || []).length}};
}}, D);
"""
    return pw.repl(body)[0]


def run(path: str, dry: bool) -> int:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    it = {"title": d["title"].strip(), "cat": d.get("category", "맛집"), "at": d.get("at"), "html": d["html"]}
    imgs = d.get("images", [])
    holders = sorted(set(int(x) for x in re.findall(r"\[\[IMG(\d+)\]\]", it["html"])))
    if holders != list(range(1, len(imgs) + 1)):
        raise Stop(GATE, f"자리표시 {holders} 와 사진 {len(imgs)}장이 안 맞음")
    for p in imgs:
        if not Path(p).exists():
            raise Stop(GATE, f"사진 없음: {p}")
    log(f"=== matjip_post {'DRY-RUN' if dry else '실행'}: {it['title']} [{it['cat']}] 사진 {len(imgs)}장" + (f" 예약 {it['at']}" if it["at"] else ""))
    if subprocess.run([pw.ASIDE_SH, "tabs"], capture_output=True, timeout=60).returncode != 0:
        raise Stop(ASIDE_DOWN, "aside.sh tabs 실패")
    lock, tid, backup, parked, clicked, keep_tab, code = pw.EditorLock(), None, None, False, False, False, OK
    result = {}
    try:
        lock.acquire()
        pw.wait_no_foreign_editor(lock)
        marker = f"mjrun={pw.TS}"
        subprocess.run([pw.ASIDE_SH, "open", f"{pw.BLOG}/manage/posts/?{marker}"], capture_output=True, timeout=60)
        for _ in range(30):
            hit = [t for t in pw.cdp_list() if marker in t.get("url", "")]
            if hit:
                tid = hit[0]["id"]
                break
            time.sleep(0.5)
        if not tid:
            raise Stop(ASIDE_DOWN, "작업 탭을 못 열었음")
        pf = pw.preflight(tid, [{"key": "post", "title": it["title"], "cat": it["cat"]}])
        if not pf.get("login"):
            raise Stop(LOGIN, f"로그인 필요 ({pf.get('href') or pf.get('why')})")
        if it["cat"] not in pf.get("cats", []):
            raise Stop(GATE, f"카테고리 '{it['cat']}' 가 블로그에 없음")
        if pf["found"]["post"]["hits"]:
            h = pf["found"]["post"]["hits"][0]
            log(f"  · 같은 제목 글이 이미 있음 → 올리지 않음: /{h['id']} {h['visibility']}")
            print(f"ALREADY\t/{h['id']}\t{h.get('permalink')}")
            return OK
        auto = pf.get("autosave")
        if isinstance(auto, str):
            raise Stop(GATE, "자동저장 상태 읽기 실패: " + auto)
        if auto is not None:
            backup = auto
            (pw.LOG_DIR / f"autosave_backup_{pw.TS}.json").write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
            r = pw.autosave_park(tid)
            if not r.get("ok"):
                raise Stop(GATE, "자동저장 슬롯을 못 비움")
            parked = True
        lock.touch()
        r = open_editor(tid, {"title": it["title"], "html": it["html"], "cat": it["cat"]})
        log(f"  편집기: {json.dumps(r, ensure_ascii=False)[:200]}")
        if r.get("login") is False:
            raise Stop(LOGIN, "로그인 필요")
        if not r.get("ok"):
            raise Stop(GATE, f"편집기 준비 실패: {r.get('error') or r.get('why')}")
        for n, p in enumerate(imgs, 1):
            lock.touch()
            key = f"i{n}"
            push_image(tid, key, p)
            pr = place_image(tid, n, key, f"matjip_{pw.TS}_{n}.jpg")
            log(f"  사진 {n}/{len(imgs)}: {json.dumps(pr, ensure_ascii=False)}")
            if not pr.get("ok"):
                raise Stop(GATE, f"사진 {n} 실패: {pr.get('why')}")
        if d.get("place"):
            lock.touch()
            pc = place_card(tid, d["place"]["query"], d["place"].get("match") or d["place"]["query"])
            log(f"  장소 카드: {json.dumps(pc, ensure_ascii=False)}")
            if not pc.get("ok"):
                raise Stop(GATE, f"장소 카드 실패: {pc.get('why')} {pc.get('all', '')}")
        vis = pw.VIS
        st, shots = open_layer(tid, {"radio": vis["radio"], "at": it["at"]})
        shot = pw.save_shot(shots, "matjip", "dry" if dry else "pre")
        g = {
            "제목": st.get("title") == it["title"],
            "카테고리": st.get("cat") == it["cat"],
            f"사진 {len(imgs)}장": st.get("figs") == len(imgs) and st.get("holders") == 0,
            "본문 있음": (st.get("edText") or 0) > 200,
            "공개": st.get("open20") and not st.get("open0") and not st.get("open15") and st.get("btnText") == vis["btn"] and st.get("btnDisabled") is False,
            "태그 없음": st.get("tags", "x") == "",
        }
        if d.get("place"):
            g["장소 카드"] = bool(st.get("place"))
        if it["at"]:
            wd, hm = it["at"].split(" ")
            hh, mm = hm.split(":")
            g["예약 일시"] = st.get("resDate") == wd and st.get("resHour") == hh and st.get("resMin") == mm
        log("  게이트: " + ", ".join(f"{k}={'O' if v else 'X'}" for k, v in g.items()) + (f"  스크린샷 {shot}" if shot else ""))
        if not all(g.values()):
            pw.cancel_layer(tid)
            raise Stop(GATE, f"게이트 실패 {[k for k, v in g.items() if not v]} — 저장 안 함")
        if dry:
            log("  DRY-RUN — 저장하지 않고 닫음")
            pw.cancel_layer(tid)
            print(f"DRYRUN\t{shot}")
            return OK
        clicked = True
        res, shots2 = pw.commit_save(tid, it, {"edText": st.get("edText")})
        log(f"  저장 클릭: {res.get('state')} {json.dumps(res.get('pre', {}).get('chk'), ensure_ascii=False)}")
        if res.get("state") == "not-clicked":
            clicked = False
            pw.cancel_layer(tid)
            raise Stop(GATE, "클릭 직전 재확인 실패 — 저장 안 함")
        if res.get("state") == "captcha":
            keep_tab = True
            lock.touch()
            rc = pw.chacap_relay(tid, it["title"])
            lock.touch()
            if rc != 0:
                raise Stop(CAPTCHA, f"CAPTCHA — 중계 rc={rc}, 편집기 탭 그대로 둠: {it['title']}")
            pw.wait_left_editor(tid)
            res["state"] = "navigated"
        if res.get("state") != "navigated":
            keep_tab = True
            raise Stop(UNVERIFIED, f"저장 결과 불명({res.get('state')}) — 재시도 금지, 사람 확인")
        v = verify(tid, it, len(imgs))
        log(f"  확인: {json.dumps(v, ensure_ascii=False)}")
        want = "RESERVED_PUBLIC" if it["at"] else "PUBLIC"
        ok = v.get("found") and v.get("visibility") == want and str(v.get("category", "")).endswith(it["cat"]) \
            and (it["at"] and str(v.get("published", "")).startswith(it["at"]) or (not it["at"] and (v.get("imgs") or 0) >= len(imgs)))
        if not ok:
            raise Stop(UNVERIFIED, f"저장했지만 확인 실패 ({json.dumps(v, ensure_ascii=False)[:200]}) — 재시도 금지")
        clicked, keep_tab = False, False
        result = v
        print(f"SAVED\t{it['title']}\t{v.get('permalink')}" + (f"\t예약 {it['at']}" if it["at"] else ""))
        notify(f"맛집 후기 발행: {it['title'][:40]}")
    except Stop as exc:
        code = exc.code
        log(f"✗ [{exc.code}] {exc.msg}")
        notify(f"[{exc.code}] {exc.msg}")
    except Exception as exc:
        import traceback
        code = UNVERIFIED if clicked else GATE
        keep_tab = keep_tab or clicked
        log("✗ 예외: " + "".join(traceback.format_exception(exc))[-800:])
    finally:
        if tid:
            try:
                log(f"자동저장 마무리: {pw.autosave_restore(tid, backup if parked else None)}")
            except Stop as exc:
                log(f"자동저장 마무리 실패: {exc.msg}")
            # 2026-11-20 대표님: 「작업이 끝나면 작업하느라 띄운 탭을 닫아야돼 … 어사이드 탭 계속 쌓여서 터질거아냐」
            # → 캡챠·확인 실패여도 탭은 닫는다(늦게 풀어도 저장이 안 되는 게 실측 — 다음 회차가 새 편집기로 다시 한다).
            if keep_tab:
                log("편집기 탭은 남기지 않고 닫음(다음 회차가 다시 시도)")
            pw.close_tab(tid)
        lock.release()
    print(f"EXIT={code}  LOG={pw.LOG_PATH}")
    return code


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("post")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        return run(a.post, a.dry_run)
    except Stop as exc:
        log(f"✗ [{exc.code}] {exc.msg}")
        print(f"EXIT={exc.code}  LOG={pw.LOG_PATH}")
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
