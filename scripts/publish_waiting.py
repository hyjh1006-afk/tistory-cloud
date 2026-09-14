# -*- coding: utf-8 -*-
"""대기 목록 괴담 → 티스토리 비공개 저장 (Aside repl). 진입점은 publish_waiting.sh — 종료 코드도 거기 적혀 있다.

한 번 실행에 종류(두 줄·단편)마다 가장 오래된 1편씩만 올린다(SKILL 의 "오늘 몫"과 같음).

2026-09-14 실측으로 정한 것:
- Aside repl 에 붙은 탭에서는 confirm() 이 **자동으로 true** 가 된다(page.on('dialog') 는 안 불린다).
  그래서 자동저장 글이 남아 있으면 "이어서 작성하시겠습니까?" 가 자동 수락돼 남의 초안이 편집기에 로드된다.
  → 편집기를 열기 전에 /manage/autosave 를 읽어, 남아 있으면 로컬 백업 후 비워 두고(park) 끝나면 되돌린다.
- 자동저장 슬롯은 DELETE 가 없다(405). 빈 값을 POST 해도 "빈 글" 로 남는다.
  **임시저장(POST /manage/drafts) 을 하면 자동저장이 비워진다** → 우리가 만든 그 임시저장만 DELETE.
- 우리 편집기 탭에서는 /manage/autosave POST 를 XHR·fetch 단계에서 막는다 → 우리 때문에 슬롯이 더러워질 일이 없다.
- 글 목록은 /manage/posts.json (화면이 쓰는 그 API) 으로 읽는다. 검색 색인 지연을 피하려고 키워드 없는 목록도 같이 본다.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BLOG = "https://tester188.tistory.com"
CDP = "http://127.0.0.1:9223"
ASIDE_SH = os.path.expanduser("~/.claude/tools/screen/aside.sh")
ASIDE = os.path.expanduser("~/.local/bin/aside")
LOCK = "/tmp/tistory-editor.lock"
LOCK_STALE_S = 20 * 60          # cedar_post.sh 와 같은 기준
LOCK_WAIT_S = int(os.environ.get("PW_LOCK_WAIT", "600"))
CATS = {"two_sentence": "두 줄 괴담", "nosleep": "단편 괴담"}
LEN_TOL = 0.02
GAP_BETWEEN_POSTS_S = 30        # 연속 저장은 DKAPTCHA 를 부른다(2026-09-07 실측: 2편째에 뜸)

OK, GATE, ASIDE_DOWN, LOGIN, UNVERIFIED, CAPTCHA, BUSY = 0, 1, 2, 4, 5, 7, 8
EDITOR_TAB_RE = re.compile(r"tistory\.com/manage/(newpost|post)(/|\?|$)")

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"publish_{TS}.log"


class Stop(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(msg: str) -> None:
    safe = msg.replace("\\", "").replace('"', "'")[:220]
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe}" with title "괴담 발행" sound name "Basso"'],
        capture_output=True, timeout=10,
    )


# ── Aside ────────────────────────────────────────────────────────────────
def cdp_list() -> list[dict]:
    with urllib.request.urlopen(CDP + "/json/list", timeout=8) as r:
        return [t for t in json.loads(r.read() or "[]") if t.get("type") == "page"]


def cdp_close(target_id: str) -> None:
    try:
        urllib.request.urlopen(CDP + "/json/close/" + target_id, timeout=8).read()
    except Exception as exc:  # 이미 닫혔으면 404
        log(f"  · 탭 닫기 응답: {exc}")


def repl(body: str, timeout: int = 150) -> tuple[dict, list[str]]:
    """body 는 async 함수 본문. return 값이 RESULT= 로 돌아온다. SHOT= 줄은 따로 모은다."""
    code = (
        "const __out = await (async () => {\n" + body + "\n})()"
        ".catch(e => ({error: String((e && e.stack) || e).slice(0, 600)}));\n"
        "console.log('RESULT=' + JSON.stringify(__out));"
    )
    try:
        p = subprocess.run([ASIDE, "repl", code], cwd="/tmp", capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Stop(ASIDE_DOWN, "aside repl 시간 초과")
    out = (p.stdout or "") + (p.stderr or "")
    if "isn't running" in out or "not running" in out.lower():
        raise Stop(ASIDE_DOWN, "Aside 가 꺼져 있음")
    res, shots = None, []
    for line in out.splitlines():
        if line.startswith("RESULT="):
            res = json.loads(line[7:])
        elif line.startswith("SHOT="):
            shots.append(line[5:])
    if res is None:
        raise Stop(ASIDE_DOWN, "aside repl 결과 없음: " + out.strip()[-300:])
    return res, shots


def attach_js(tid: str) -> str:
    return (
        f"const TID = {json.dumps(tid)};\n"
        # 방금 연 탭은 Aside 목록에 늦게 잡힌다(CDP 목록보다 1~2초 느림, 2026-09-14 실측)
        "let __seen = false;\n"
        "for (let i = 0; i < 40 && !__seen; i++) { __seen = (await listBrowserTabs()).some(x => x.targetId === TID); if (!__seen) await sleep(250); }\n"
        "if (!__seen) return {error: 'notab'};\n"
        "const P = await attachBrowserTab(TID);\n"
    )


# 페이지 안에서 쓰는 공통 함수 (evaluate 인자로 문자열을 넘겨 eval 하지 않고, 필요할 때마다 인라인)
J_FN = (
    "const F = window.__pwOrigFetch || window.fetch; const J = async (u, o) => { const r = await F(u, Object.assign({credentials:'include', headers:{'Accept':'application/json'}}, o||{}));"
    " const t = await r.text(); try { return {s:r.status, j:JSON.parse(t)}; } catch(e) { return {s:r.status, t:t.slice(0,200)}; } };"
)
DRAFT_CLEAR_FN = (
    # 자동저장 슬롯 비우기: 임시저장 1건 만들고(→ 서버가 자동저장을 지움) 그 1건만 지운다.
    "const clearAutosave = async () => {"
    " const H = {'Accept':'application/json, text/plain, */*','Content-Type':'application/json'};"
    " const before = ((await J('/manage/drafts')).j?.data || []).map(d => d.sequence);"
    " const r = await F('/manage/drafts', {method:'POST', credentials:'include', headers:H,"
    "   body: JSON.stringify({title:'[publish_waiting] 자동저장 초기화용 — 곧 지워짐', content:'<p>-</p>', tags:'', categoryId:0, thumbnail:null, totalWritingTimeMs:0})});"
    " const pj = await r.json().catch(() => ({})); const seq = pj?.draft?.sequence;"
    " if (seq == null || before.includes(seq)) return {ok:false, why:'draft seq '+seq};"
    " const d = await F('/manage/drafts/' + seq, {method:'DELETE', credentials:'include', headers:{'Accept':'application/json'}});"
    " const after = (await J('/manage/autosave')).j;"
    " const left = ((await J('/manage/drafts')).j?.data || []).map(x => x.sequence);"
    " return {ok: !!after && after.autosavedEntry === null && !left.includes(seq), seq, del: d.status};"
    "};"
)


# ── 잠금 ────────────────────────────────────────────────────────────────
class EditorLock:
    def __init__(self) -> None:
        self.token = f"{os.getpid()} publish_waiting {datetime.now().isoformat(timespec='seconds')}"
        self.held = False

    def acquire(self) -> None:
        deadline = time.time() + LOCK_WAIT_S
        said = False
        while True:
            try:
                os.mkdir(LOCK)
                Path(LOCK, "owner").write_text(self.token + "\n", encoding="utf-8")
                self.held = True
                log(f"잠금 획득 {LOCK}")
                return
            except FileExistsError:
                age = time.time() - os.path.getmtime(LOCK)
                if age > LOCK_STALE_S:
                    log(f"  · {int(age/60)}분 묵은 잠금 회수")
                    shutil.rmtree(LOCK, ignore_errors=True)
                    continue
                owner = (Path(LOCK, "owner").read_text(encoding="utf-8").strip() if Path(LOCK, "owner").exists() else "?")
                if time.time() > deadline:
                    raise Stop(BUSY, f"편집기 잠금 사용 중: {owner}")
                if not said:
                    log(f"  … 잠금 대기 ({owner})")
                    said = True
                time.sleep(20)

    def touch(self) -> None:
        if self.held:
            try:
                os.utime(LOCK)
            except OSError:
                pass

    def release(self) -> None:
        if not self.held:
            return
        try:
            if Path(LOCK, "owner").read_text(encoding="utf-8").strip() == self.token:
                shutil.rmtree(LOCK, ignore_errors=True)
                log("잠금 해제")
        except OSError:
            pass
        self.held = False


def wait_no_foreign_editor(lock: EditorLock) -> None:
    deadline = time.time() + LOCK_WAIT_S
    said = False
    while True:
        busy = [t["url"] for t in cdp_list() if EDITOR_TAB_RE.search(t.get("url", ""))]
        if not busy:
            return
        if time.time() > deadline:
            raise Stop(BUSY, "다른 편집기 탭이 열려 있음: " + ", ".join(u[-60:] for u in busy))
        if not said:
            log("  … 다른 편집기 탭 사용 중 — 대기: " + ", ".join(u[-60:] for u in busy))
            said = True
        lock.touch()
        time.sleep(20)


# ── 대기 목록 ────────────────────────────────────────────────────────────
def load_items(fixture: str | None) -> list[dict]:
    if fixture:
        d = json.loads(Path(fixture).read_text(encoding="utf-8"))
        if not d.get("title", "").startswith("[DRYRUN-TEST]"):
            d["title"] = "[DRYRUN-TEST] " + d["title"]
        d["_name"], d["_sha"] = Path(fixture).name, None
        rows = [d]
    else:
        import github_state
        rows = github_state.list_outputs()
    items = []
    for o in rows:
        mode = o.get("mode")
        if mode not in CATS:          # cedar_remaster 등 다른 대기물은 이 스크립트 소관 아님
            continue
        html = o.get("html") or ""
        items.append({
            "key": o["_name"], "sha": o.get("_sha"), "mode": mode, "cat": CATS[mode],
            "title": (o.get("title") or "").strip(), "html": html,
            "links": re.findall(r'href="(https://www\.reddit\.com/r/[^"]+)"', html),
            "authors": re.findall(r"작성자:\s*(u/[A-Za-z0-9_-]+)", html),
        })
    picked, seen = [], set()
    for it in sorted(items, key=lambda x: x["key"]):  # 파일명 앞이 생성 시각 → 오래된 것부터
        if it["mode"] in seen:
            log(f"  · 이번 회차에서 미룸(같은 종류 1편만): {it['key']}")
            continue
        seen.add(it["mode"])
        picked.append(it)
    return picked


def mark_done(it: dict, dry: bool) -> None:
    if dry or not it.get("sha"):
        log(f"  · DRY-RUN: 대기 목록에서 지울 예정 → {it['key']}")
        return
    import github_state
    github_state.delete_output(it["key"], it["sha"])
    log(f"  · 대기 목록에서 제거: {it['key']}")


# ── 단계별 repl ──────────────────────────────────────────────────────────
def preflight(tid: str, items: list[dict]) -> dict:
    args = [{"key": i["key"], "title": i["title"], "cat": i["cat"]} for i in items]
    body = attach_js(tid) + f"""
for (let i = 0; i < 30; i++) {{ if (!/about:blank/.test(P.url())) break; await sleep(300); }}
await sleep(1500);
const href = P.url();
if (/auth\\/login|accounts\\.kakao\\.com|\\/login\\b/.test(href) || !/tester188\\.tistory\\.com\\/manage/.test(href)) return {{login:false, href}};
return await P.evaluate(async (items) => {{
  {J_FN}
  const cats = await J('/manage/category/simple.json');
  if (!cats.j || !cats.j.categories) return {{login:false, why:'category.json '+cats.s}};
  const flat = []; const walk = a => a.forEach(c => {{ flat.push({{id:c.id, name:c.name, label:c.label}}); walk(c.children||[]); }}); walk(cats.j.categories);
  const auto = await J('/manage/autosave');
  const found = {{}};
  for (const it of items) {{
    const cid = (flat.find(c => c.name === it.cat) || {{}}).id;
    const q = (cat, vis, kw) => '/manage/posts.json?category='+cat+'&page=1&searchKeyword='+encodeURIComponent(kw)+'&searchType=title&visibility='+vis;
    const hits = [];
    for (const u of [q(cid ?? -3, 'all', ''), q(-3, 'hidden', ''), q(-3, 'all', it.title)]) {{
      const r = await J(u);
      for (const p of ((r.j && r.j.items) || [])) if (p.title === it.title && !hits.some(h => h.id === p.id))
        hits.push({{id:p.id, visibility:p.visibility, category:p.category, created:p.created, permalink:p.permalink}});
    }}
    found[it.key] = {{catId: cid ?? null, hits}};
  }}
  return {{login:true, cats:flat.map(c=>c.name), autosave: auto.j ? auto.j.autosavedEntry : 'ERR '+auto.s, found}};
}}, {json.dumps(args, ensure_ascii=False)});
"""
    res, _ = repl(body)
    return res


def autosave_park(tid: str) -> dict:
    body = attach_js(tid) + f"""
return await P.evaluate(async () => {{ {J_FN} {DRAFT_CLEAR_FN} return await clearAutosave(); }});
"""
    return repl(body)[0]


def autosave_restore(tid: str, backup: dict | None) -> dict:
    """끝 상태를 시작 상태로 되돌린다. backup=None 이면 '비어 있어야 함'."""
    body = attach_js(tid) + f"""
return await P.evaluate(async (bk) => {{
  {J_FN} {DRAFT_CLEAR_FN}
  const cur = (await J('/manage/autosave')).j;
  if (!cur) return {{ok:false, why:'autosave 읽기 실패'}};
  const now = cur.autosavedEntry;
  if (!bk) {{
    if (now === null) return {{ok:true, state:'clean'}};
    const c = await clearAutosave(); return {{ok:c.ok, state:'cleared-our-leftover', c}};
  }}
  if (now !== null) return {{ok:true, state:'someone-wrote-newer — 백업 복원 생략', now: String(now.title).slice(0,40)}};
  const H = {{'Accept':'application/json, text/plain, */*','Content-Type':'application/json'}};
  const r = await F('/manage/autosave', {{method:'POST', credentials:'include', headers:H, body: JSON.stringify({{
    title:bk.title||'', content:bk.content||'', tags:bk.tags||'', categoryId:bk.categoryId||0, thumbnail:bk.thumbnail||null,
    draftSequence:bk.draftSequence||null, totalWritingTimeMs:bk.totalWritingTimeMs||0}})}});
  const back = (await J('/manage/autosave')).j;
  return {{ok: r.status === 200 && !!(back && back.autosavedEntry), state:'restored-foreign'}};
}}, {json.dumps(backup, ensure_ascii=False)});
"""
    return repl(body)[0]


def prepare_editor(tid: str, it: dict, dry: bool = False) -> tuple[dict, list[str]]:
    d = {"title": it["title"], "html": it["html"], "cat": it["cat"], "typed": it["title"]}
    # 게이트가 진짜 잡는지 반증용 (dry-run 에서만): PW_TEST_BREAK=title 이면 제목을 일부러 틀리게 친다
    if dry and os.environ.get("PW_TEST_BREAK") == "title":
        d["typed"] = it["title"] + " X"
    body = attach_js(tid) + f"""
const D = {json.dumps(d, ensure_ascii=False)};
await P.goto({json.dumps(BLOG + "/manage/newpost/")});
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
  // 우리 탭의 자동저장 POST 차단 — 블로그당 하나뿐인 슬롯을 더럽히지 않는다
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
  const cleanBefore = {{title: document.querySelector('#post-title-inp').value, body: norm(ed.getBody().textContent).length}};
  if (cleanBefore.title !== '' || cleanBefore.body !== 0) return {{ok:false, why:'편집기가 비어 있지 않음(남의 초안?)', cleanBefore}};
  document.querySelector('#category-btn').click();
  await new Promise(r => setTimeout(r, 700));
  const opts = [...document.querySelectorAll('#category-list li, #category-list [role=option]')];
  const opt = opts.find(e => e.textContent.trim().replace(/^-\\s*/, '') === D.cat);
  if (!opt) return {{ok:false, why:'카테고리 항목 없음: '+D.cat, opts: opts.map(e=>e.textContent.trim())}};
  opt.click();
  await new Promise(r => setTimeout(r, 500));
  ed.focus(); ed.selection.select(ed.getBody(), true);
  const dt = new DataTransfer();
  dt.setData('text/html', D.html); dt.setData('text/plain', D.html.replace(/<[^>]+>/g, ''));
  ed.getBody().dispatchEvent(new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}}));
  await new Promise(r => setTimeout(r, 1500));
  const srcText = norm(new DOMParser().parseFromString(D.html, 'text/html').body.textContent).length;
  const edText = norm(ed.getBody().textContent).length;
  const t = document.querySelector('#post-title-inp'); t.focus(); t.setSelectionRange(0, t.value.length);
  return {{ok:true, srcText, edText, active: document.activeElement.id}};
}}, D);
if (!s1.ok) return s1;
await P.keyboard.insertText(D.typed);   // 제목은 진짜 입력으로 (JS value 대입은 저장 때 되돌아간다)
await sleep(600);
const s2 = await P.evaluate(async (D) => {{
  const title = document.querySelector('#post-title-inp').value;
  const tags = ((document.querySelector('.editor_tag') || {{}}).innerText || '').replace(/#/g, '').trim();
  const cat = document.querySelector('#category-btn').textContent.replace(/더보기\\s*$/, '').trim();
  const done = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '완료');
  if (!done) return {{ok:false, why:'완료 버튼 없음'}};
  done.click();
  let o0 = null;
  for (let i = 0; i < 20 && !o0; i++) {{ await new Promise(r => setTimeout(r, 250)); o0 = document.getElementById('open0'); }}
  if (!o0) return {{ok:false, why:'발행 레이어 안 뜸', title, tags, cat}};
  (document.querySelector('label[for=open0]') || o0.parentElement).click();
  await new Promise(r => setTimeout(r, 800));
  const btn = document.getElementById('publish-btn');
  const vis = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null).map(b => b.textContent.trim()).filter(Boolean);
  return {{ok:true, title, tags, cat,
    open0: document.getElementById('open0').checked, open15: !!document.getElementById('open15')?.checked, open20: !!document.getElementById('open20')?.checked,
    btnText: btn ? btn.textContent.trim() : null, btnDisabled: btn ? btn.disabled : null,
    saving: vis.includes('저장중'), blocked: window.__pwBlocked}};
}}, D);
const shot = await P.screenshot({{type:'jpeg', quality:55}});
console.log('SHOT=' + shot.toString('base64'));
return Object.assign({{}}, s1, s2);
"""
    return repl(body)


def gates(it: dict, r: dict) -> dict[str, bool]:
    src, got = r.get("srcText") or 0, r.get("edText") or 0
    return {
        "제목 일치": r.get("title") == it["title"],
        "본문 있음": got > 0 and src > 0,
        "본문 길이 ±2%": src > 0 and abs(got - src) / src <= LEN_TOL,
        "비공개": bool(r.get("open0")) and not r.get("open15") and not r.get("open20")
                 and r.get("btnText") == "비공개 저장" and r.get("btnDisabled") is False,
        "카테고리": r.get("cat") == it["cat"],
        "태그 없음": r.get("tags", "x") == "",
        "저장중 아님": not r.get("saving"),
    }


def cancel_layer(tid: str) -> None:
    body = attach_js(tid) + """
return await P.evaluate(async () => {
  const c = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '취소' && b.offsetParent !== null);
  if (c) c.click();
  await new Promise(r => setTimeout(r, 600));
  return {ok:true, layerGone: ![...document.querySelectorAll('button')].some(b => b.textContent.trim() === '비공개 저장' && b.offsetParent !== null), blocked: window.__pwBlocked};
});
"""
    try:
        log(f"  · 발행 레이어 닫음 {repl(body)[0]}")
    except Stop as exc:
        log(f"  · 레이어 닫기 실패: {exc.msg}")


def commit_save(tid: str, it: dict, prepared: dict) -> tuple[dict, list[str]]:
    d = {"title": it["title"], "cat": it["cat"], "edText": prepared.get("edText")}
    body = attach_js(tid) + f"""
const D = {json.dumps(d, ensure_ascii=False)};
// 클릭 직전, 같은 틱에서 전부 다시 확인한다. 하나라도 어긋나면 누르지 않는다.
const pre = await P.evaluate((D) => {{
  const norm = s => (s || '').replace(/\\s+/g, '');
  const o0 = document.getElementById('open0'), o15 = document.getElementById('open15'), o20 = document.getElementById('open20');
  const btn = document.getElementById('publish-btn');
  const chk = {{
    title: document.querySelector('#post-title-inp')?.value === D.title,
    cat: document.querySelector('#category-btn')?.textContent.replace(/더보기\\s*$/, '').trim() === D.cat,
    body: norm(tinymce.get('editor-tistory').getBody().textContent).length === D.edText,
    private: !!o0 && o0.checked && !(o15 && o15.checked) && !(o20 && o20.checked),
    button: !!btn && btn.textContent.trim() === '비공개 저장' && !btn.disabled && btn.offsetParent !== null,
  }};
  if (!Object.values(chk).every(Boolean)) return {{clicked:false, chk}};
  btn.click();
  return {{clicked:true, chk}};
}}, D);
if (!pre.clicked) return {{state:'not-clicked', pre}};
let state = 'unknown', busyFor = 0, last = null;
for (let i = 0; i < 45; i++) {{
  await sleep(1000);
  const u = P.url();
  if (!/\\/manage\\/newpost/.test(u)) {{ state = 'navigated'; last = u; break; }}
  let st = null;
  try {{
    st = await P.evaluate(() => {{
      const vis = f => f.offsetHeight > 50 && getComputedStyle(f).visibility !== 'hidden';
      const modal = [...document.querySelectorAll('[role=dialog],[role=alertdialog],.layer_modal,.modal,.layer_alert')].filter(e => e.offsetParent !== null).map(e => e.innerText).join(' ').slice(0, 200);
      return {{
        busy: [...document.querySelectorAll('button')].some(b => (b.innerText || '').trim() === '저장중'),
        dk: !!document.querySelector('iframe[src*="dkaptcha"]') || /DKAPTCHA|지도에서|빈칸에 들어갈/.test(document.body.innerText),
        rc: [...document.querySelectorAll('iframe[src*="recaptcha"]')].some(vis),
        modal, layer: [...document.querySelectorAll('button')].some(b => b.textContent.trim() === '비공개 저장' && b.offsetParent !== null),
      }};
    }});
  }} catch (e) {{ continue; }}          // 페이지 이동 중이면 평가가 끊긴다
  last = st;
  if (st.dk || st.rc) {{ state = 'captcha'; break; }}
  if (/Bad Request|오류|실패|못했습니다/.test(st.modal)) {{ state = 'error'; break; }}
  busyFor = st.busy ? busyFor + 1 : 0;
  if (busyFor >= 15) {{ state = 'captcha'; break; }}   // '저장중' 에서 멈춤 = 캡챠(교차 출처 iframe 이라 안이 안 보일 때)
}}
if (state !== 'navigated') {{ try {{ const s = await P.screenshot({{type:'jpeg', quality:55}}); console.log('SHOT=' + s.toString('base64')); }} catch (e) {{}} }}
return {{state, pre, last}};
"""
    return repl(body, timeout=170)


def verify_saved(tid: str, it: dict, cat_id) -> dict:
    d = {"title": it["title"], "cat": it["cat"], "catId": cat_id, "nLinks": len(it["links"])}
    body = attach_js(tid) + f"""
const D = {json.dumps(d, ensure_ascii=False)};
if (!/tester188\\.tistory\\.com\\/manage/.test(P.url())) {{ await P.goto({json.dumps(BLOG + "/manage/posts/")}); await sleep(2500); }}
return await P.evaluate(async (D) => {{
  {J_FN}
  const q = (cat, vis, kw) => '/manage/posts.json?category='+cat+'&page=1&searchKeyword='+encodeURIComponent(kw||'')+'&searchType=title&visibility='+vis;
  let hit = null;
  for (let a = 0; a < 4 && !hit; a++) {{
    if (a) await new Promise(r => setTimeout(r, 4000));
    for (const u of [q(-3, 'hidden'), q(D.catId ?? -3, 'all'), q(-3, 'all', D.title)]) {{
      const r = await J(u);
      hit = ((r.j && r.j.items) || []).find(p => p.title === D.title);
      if (hit) break;
    }}
  }}
  if (!hit) return {{found:false}};
  const r = await F(hit.permalink || ('/' + hit.id), {{cache:'no-store', credentials:'include'}});
  const t = await r.text();
  const reddit = (t.match(/reddit\\.com\\/r\\//g) || []).length;
  return {{found:true, id:hit.id, visibility:hit.visibility, category:hit.category, permalink:hit.permalink,
    page:r.status, pageTitle:(t.match(/<title>([^<]*)<\\/title>/) || [])[1], srcLink: t.includes('원문 링크'), reddit}};
}}, D);
"""
    return repl(body)[0]


def close_tab(tid: str) -> None:
    t0 = time.time()
    # 편집 중인 탭은 beforeunload 가 걸려 있다 — 붙은 상태에서 about:blank 로 빼낸 뒤(확인창은 repl 이 자동 수락) 닫는다
    try:
        # goto 로 빼내면 beforeunload 확인창에 걸려 30초를 먹는다(2026-09-14 실측) → 캡처 단계에서 편집기의 핸들러를 막고 바로 닫는다
        repl(attach_js(tid) + "try { await P.evaluate(() => window.addEventListener('beforeunload', e => e.stopImmediatePropagation(), true)); } catch (e) {} return {ok:true};", timeout=40)
    except Stop:
        pass
    cdp_close(tid)
    time.sleep(1)
    left = any(t["id"] == tid for t in cdp_list())
    log(f"  · 작업 탭 닫음 ({time.time() - t0:.0f}초){' ⚠ 아직 남아 있음' if left else ''}")


def save_shot(shots: list[str], key: str, tag: str) -> str | None:
    if not shots:
        return None
    p = LOG_DIR / f"publish_{TS}_{tag}_{re.sub(r'[^0-9A-Za-z_.-]', '_', key)[:40]}.jpg"
    p.write_bytes(base64.b64decode(shots[-1]))
    return str(p)


# ── 본체 ────────────────────────────────────────────────────────────────
def run(args) -> int:
    dry = args.dry_run or bool(args.fixture)
    log(f"=== publish_waiting {'DRY-RUN' if dry else '실행'} {('fixture='+args.fixture) if args.fixture else ''}")
    items = load_items(args.fixture)
    if not items:
        log("올릴 괴담 없음 (대기 목록에 두 줄·단편 없음)")
        return OK
    for it in items:
        log(f"대상: {it['key']} [{it['cat']}] {it['title']} (본문 {len(it['html'])}자, 원문 {len(it['links'])}개)")
        if not it["title"] or not it["html"]:
            raise Stop(GATE, f"제목/본문 비어 있음: {it['key']}")

    # Aside 살아 있나 (aside.sh 가 CDP 포트를 보장한다)
    if subprocess.run([ASIDE_SH, "tabs"], capture_output=True, timeout=60).returncode != 0:
        raise Stop(ASIDE_DOWN, "aside.sh tabs 실패")
    repl("return {ok:true};", timeout=40)

    lock = EditorLock()
    tid = None
    backup = None
    parked = False
    editor_opened = False
    clicked = False          # 저장 버튼을 누른 뒤의 예외는 "저장됐을 수도 있음"(5)으로 다룬다
    keep_tab = False
    summary: list[dict] = []
    code = OK
    try:
        lock.acquire()
        wait_no_foreign_editor(lock)
        marker = f"pwrun={TS}"
        subprocess.run([ASIDE_SH, "open", f"{BLOG}/manage/posts/?{marker}"], capture_output=True, timeout=60)
        for _ in range(30):
            hit = [t for t in cdp_list() if marker in t.get("url", "")]
            if hit:
                tid = hit[0]["id"]
                break
            time.sleep(0.5)
        if not tid:
            raise Stop(ASIDE_DOWN, "작업 탭을 못 열었음")

        pf = preflight(tid, items)
        if pf.get("error"):
            raise Stop(GATE, "사전 점검 오류: " + pf["error"])
        if not pf.get("login"):
            raise Stop(LOGIN, f"로그인 필요 ({pf.get('href') or pf.get('why')})")
        for c in CATS.values():
            if c not in pf.get("cats", []):
                raise Stop(GATE, f"카테고리 '{c}' 가 블로그에 없음")
        auto = pf.get("autosave")
        if isinstance(auto, str):
            raise Stop(GATE, "자동저장 상태 읽기 실패: " + auto)

        todo = []
        for it in items:
            f = pf["found"].get(it["key"], {})
            it["catId"] = f.get("catId")
            if f.get("hits"):
                h = f["hits"][0]
                log(f"  · 이미 있음 → 다시 올리지 않음: /{h['id']} {h['visibility']} {h['category']} ({h['created']})")
                mark_done(it, dry)
                summary.append({"key": it["key"], "result": "already", "id": h["id"], "visibility": h["visibility"],
                                "url": h.get("permalink")})
            else:
                todo.append(it)
        if not todo:
            log("새로 저장할 글 없음")

        if todo and auto is not None:
            # 남이 남긴 자동저장 → 편집기를 열면 자동 수락돼 로드된다. 백업 후 비우고, 끝에 되돌린다.
            backup = auto
            bpath = LOG_DIR / f"autosave_backup_{TS}.json"
            bpath.write_text(json.dumps(auto, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"  · 남아 있던 자동저장 백업 → {bpath.name} (제목: {str(auto.get('title'))[:40]!r})")
            r = autosave_park(tid)
            log(f"  · 자동저장 비움 {r}")
            if not r.get("ok"):
                raise Stop(GATE, "자동저장 슬롯을 못 비움")
            parked = True

        for n, it in enumerate(todo):
            lock.touch()
            if n:
                log(f"  … 연속 저장 간격 {GAP_BETWEEN_POSTS_S}초")
                time.sleep(GAP_BETWEEN_POSTS_S)
            log(f"▶ {it['title']}")
            editor_opened = True
            prep, shots = prepare_editor(tid, it, dry)
            shot = save_shot(shots, it["key"], "dry" if dry else "pre")
            if prep.get("login") is False:
                raise Stop(LOGIN, f"로그인 필요 ({prep.get('href')})")
            if prep.get("error") or not prep.get("ok"):
                cancel_layer(tid)
                raise Stop(GATE, f"편집기 준비 실패: {prep.get('error') or prep.get('why')} {json.dumps({k: v for k, v in prep.items() if k not in ('ok',)}, ensure_ascii=False)[:300]}")
            g = gates(it, prep)
            log("  게이트: " + ", ".join(f"{k}={'O' if v else 'X'}" for k, v in g.items())
                + f"  (본문 {prep.get('edText')}/{prep.get('srcText')}자, 자동저장 차단 {prep.get('blocked')}회)")
            if shot:
                log(f"  스크린샷: {shot}")
            if not all(g.values()):
                cancel_layer(tid)
                bad = [k for k, v in g.items() if not v]
                raise Stop(GATE, f"게이트 실패 {bad} — 저장 안 함")
            if dry:
                log(f"  DRY-RUN would save: {it['title']} [{it['cat']}] 비공개")
                cancel_layer(tid)
                summary.append({"key": it["key"], "result": "dry-run", "screenshot": shot})
                continue

            clicked = True
            res, shots2 = commit_save(tid, it, prep)
            shot2 = save_shot(shots2, it["key"], "after")
            log(f"  저장 클릭 결과: {res.get('state')} {json.dumps(res.get('pre', {}).get('chk'), ensure_ascii=False)}"
                + (f" 스크린샷 {shot2}" if shot2 else ""))
            if res.get("state") == "not-clicked":
                clicked = False
                cancel_layer(tid)
                raise Stop(GATE, "클릭 직전 재확인 실패 — 저장 안 함")
            if res.get("state") == "captcha":
                keep_tab = True
                raise Stop(CAPTCHA, f"CAPTCHA — Aside 편집기 탭에 원고 그대로 둠: {it['title']}")
            if res.get("state") != "navigated":
                keep_tab = True
                raise Stop(UNVERIFIED, f"저장 결과 불명({res.get('state')}, {str(res.get('last'))[:160]}) — 재시도 금지, 사람 확인")

            v = verify_saved(tid, it, it.get("catId"))
            log(f"  확인: {json.dumps(v, ensure_ascii=False)}")
            if v.get("found") and v.get("visibility") != "PRIVATE":
                raise Stop(UNVERIFIED, f"🚨 비공개가 아닌 상태로 저장됨: /{v.get('id')} {v.get('visibility')} — 즉시 확인")
            ok = (v.get("found") and v.get("visibility") == "PRIVATE" and str(v.get("category", "")).endswith(it["cat"])
                  and v.get("srcLink") and (v.get("reddit") or 0) >= max(1, len(it["links"])))
            if not ok:
                raise Stop(UNVERIFIED, f"저장했지만 확인 실패: {it['title']} ({json.dumps(v, ensure_ascii=False)[:200]}) — 재시도 금지")
            mark_done(it, dry)
            clicked = False
            summary.append({"key": it["key"], "result": "saved-private", "id": v["id"], "url": v.get("permalink"),
                            "title": it["title"], "sources": list(zip(it["authors"], it["links"]))})
            log(f"  ✓ 비공개 저장 확인: {v.get('permalink')}")
    except Stop as exc:
        code = exc.code
        log(f"✗ [{exc.code}] {exc.msg}")
        notify(f"[{exc.code}] {exc.msg}")
    except Exception as exc:
        import traceback
        code = UNVERIFIED if clicked else GATE
        keep_tab = keep_tab or clicked
        log("✗ 예외: " + "".join(traceback.format_exception(exc))[-800:])
        notify(f"[{code}] 예외로 중단: {exc}")
    finally:
        if tid and (parked or editor_opened):
            try:
                r = autosave_restore(tid, backup if parked else None)
                log(f"자동저장 마무리: {r}")
                if not r.get("ok"):
                    notify("자동저장 슬롯 정리 실패 — logs 확인")
                    code = code or GATE
            except Stop as exc:
                log(f"자동저장 마무리 실패: {exc.msg}")
        if tid:
            if keep_tab:
                log("편집기 탭은 사람이 보도록 열어 둠")
            else:
                close_tab(tid)
        lock.release()

    (LOG_DIR / f"publish_{TS}.json").write_text(json.dumps({"exit": code, "dry": dry, "items": summary}, ensure_ascii=False, indent=1), encoding="utf-8")
    for s in summary:
        if s["result"] == "saved-private":
            print(f"SAVED\t{s['title']}\t{s['url']}")
            for a, l in s["sources"]:
                print(f"SOURCE\t{a}\t{l}")
        elif s["result"] == "already":
            print(f"ALREADY\t{s['key']}\t/{s['id']} {s['visibility']}")
        else:
            print(f"DRYRUN\t{s['key']}\t{s.get('screenshot')}")
    if code == OK and not dry and any(s["result"] == "saved-private" for s in summary):
        notify(f"괴담 {sum(s['result'] == 'saved-private' for s in summary)}편 비공개 저장 완료")
    print(f"EXIT={code}  LOG={LOG_PATH}")
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixture")
    args = ap.parse_args()
    try:
        return run(args)
    except Stop as exc:           # 잠금·탭을 잡기 전 단계의 실패
        log(f"✗ [{exc.code}] {exc.msg}")
        notify(f"[{exc.code}] {exc.msg}")
        print(f"EXIT={exc.code}  LOG={LOG_PATH}")
        return exc.code
    except Exception as exc:     # 예상 못 한 오류 — 저장 클릭 전이면 1, 뒤면 run() 안에서 5 로 잡힌다
        import traceback
        log("✗ 예외: " + "".join(traceback.format_exception(exc))[-800:])
        notify(f"예외로 중단: {exc}")
        return GATE


if __name__ == "__main__":
    raise SystemExit(main())
