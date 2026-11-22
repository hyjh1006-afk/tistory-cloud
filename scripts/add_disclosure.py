# -*- coding: utf-8 -*-
"""이미 올라간 쿠팡 링크 글 맨 위에 대가성 고지 상자를 끼워 넣는다 (한 편씩, 저장마다 캡챠는 CHACAP 으로 대표님 텔레그램).

2026-11-22 대표님: 「지금까지 올라간 글들 전부 그렇게 수정하고」 「캡챠 93번 풀어도 되지 머 … 빨리빨리 처리해주면」.
본문은 다시 붙여넣지 않는다 — 편집기 본문 맨 앞에 blockquote 하나만 DOM 으로 넣고(예전 맨 밑 회색 고지 문단은 지움),
진짜 키(공백→Backspace)로 편집기 모델을 갱신한 뒤 저장한다. 제목·분류·공개·사진 수가 그대로인지 저장 전에 본다.

사용: scripts/add_disclosure.sh <글번호...>   — 이미 고지가 맨 위에 있는 글은 건너뛴다.
기록: logs/disclosure_done.txt (고친 글 번호), 실패는 logs/disclosure_fail.txt
종료 코드: 0 전부 정상 · 그 밖은 마지막 실패 코드(publish_waiting 과 같은 뜻)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_waiting as pw  # noqa: E402
import matjip_post as mp  # noqa: E402
from publish_waiting import Stop, OK, GATE, ASIDE_DOWN, LOGIN, UNVERIFIED, CAPTCHA, log  # noqa: E402
from src.disclosure import DISCLOSURE_TEXT  # noqa: E402

DONE = pw.LOG_DIR / "disclosure_done.txt"
FAIL = pw.LOG_DIR / "disclosure_fail.txt"


def public_state(pid: str) -> dict:
    req = urllib.request.Request(f"{pw.BLOG}/{pid}?nc={int(time.time())}", headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    t = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    body = t.split("contents_style", 1)[1] if "contents_style" in t else ""
    first = re.search(r"<(p|blockquote|figure|h\d|div)\b[^>]*>(.*?)</\1>", body[body.find(">") + 1:], re.S)
    return {"coupang": body.count("link.coupang.com"), "imgs": body.split("<!-- System - START -->")[0].count("<img "),
            "top": bool(first and first.group(1) == "blockquote" and "쿠팡 파트너스 활동" in first.group(2)),
            "bottomGrey": DISCLOSURE_TEXT in body and not (first and "쿠팡 파트너스 활동" in first.group(2))}


def edit_one(pid: str) -> int:
    before = public_state(pid)
    if before["top"]:
        log(f"/{pid}: 이미 맨 위에 고지 있음 — 건너뜀")
        return OK
    if not before["coupang"]:
        log(f"/{pid}: 쿠팡 링크 없음 — 건너뜀")
        return OK
    lock, tid, clicked, code = pw.EditorLock(), None, False, OK
    title = ""
    try:
        lock.acquire()
        pw.wait_no_foreign_editor(lock)
        marker = f"discrun={pw.TS}_{pid}"
        subprocess.run([pw.ASIDE_SH, "open", f"{pw.BLOG}/manage/posts/?{marker}"], capture_output=True, timeout=60)
        for _ in range(30):
            hit = [t for t in pw.cdp_list() if marker in t.get("url", "")]
            if hit:
                tid = hit[0]["id"]
                break
            time.sleep(0.5)
        if not tid:
            raise Stop(ASIDE_DOWN, "작업 탭을 못 열었음")
        r = pw.repl(pw.attach_js(tid) + f"""
const D = {json.dumps({"id": pid, "text": DISCLOSURE_TEXT}, ensure_ascii=False)};
await P.goto({json.dumps(pw.BLOG)} + '/manage/newpost/' + D.id + '?type=post&returnURL=ENTRY');
let ready = false;
for (let i = 0; i < 50; i++) {{
  if (/auth\\/login|accounts\\.kakao\\.com/.test(P.url())) return {{login:false, href:P.url()}};
  try {{ ready = await P.evaluate(() => !!document.querySelector('#post-title-inp') && !!(window.tinymce && tinymce.get('editor-tistory')) && tinymce.get('editor-tistory').getBody().textContent.length > 50 && !!document.querySelector('#category-btn')); }} catch (e) {{}}
  if (ready) break; await sleep(400);
}}
if (!ready) return {{error:'편집기가 안 뜸', href:P.url()}};
await sleep(1500);
return await P.evaluate((D) => {{
  const ed = tinymce.get('editor-tistory'); const doc = ed.getBody();
  const figs = () => [...doc.querySelectorAll('figure img')].filter(i => /kakaocdn|daumcdn|tistory/.test(i.getAttribute('src') || '')).length;
  const f0 = figs();
  // 예전 맨 밑 회색 고지 문단은 지운다(맨 위 상자 하나만 남긴다)
  let removed = 0;
  [...doc.querySelectorAll('p')].forEach(p => {{ if (p.textContent.trim() === D.text) {{ p.remove(); removed++; }} }});
  const bq = ed.dom.create('blockquote', {{'data-ke-style': 'style3'}}, D.text);
  doc.insertBefore(bq, doc.firstChild);
  ed.setDirty(true); ed.fire('change');
  return {{ok:true, title: document.querySelector('#post-title-inp').value,
    cat: document.querySelector('#category-btn').textContent.replace(/더보기\\s*$/, '').trim(), figs0: f0, figs1: figs(), removed}};
}}, D);
""")[0]
        if r.get("login") is False:
            raise Stop(LOGIN, f"로그인 필요 ({r.get('href')})")
        if not r.get("ok"):
            raise Stop(GATE, f"편집기 준비 실패: {r.get('error')}")
        title = r["title"]
        log(f"/{pid} 「{title[:40]}」 [{r['cat']}] 사진 {r['figs0']} · 옛 고지 지움 {r['removed']}")
        mp.real_key(tid)
        it = {"title": title, "cat": r["cat"], "at": None, "html": "link.coupang.com"}
        st, shots = mp.open_layer(tid, {"radio": pw.VIS["radio"], "at": None})
        g = {
            "제목": st.get("title") == title,
            "분류": st.get("cat") == r["cat"],
            "사진 수 그대로": st.get("figs") == r["figs0"],
            "고지 맨 위": bool(st.get("disc")),
            "공개": st.get("open20") and not st.get("open0") and not st.get("open15") and st.get("btnText") == pw.VIS["btn"] and st.get("btnDisabled") is False,
        }
        log("  게이트: " + ", ".join(f"{k}={'O' if v else 'X'}" for k, v in g.items()))
        if not all(g.values()):
            pw.save_shot(shots, f"disc{pid}", "gate")
            pw.cancel_layer(tid)
            raise Stop(GATE, f"게이트 실패 {[k for k, v in g.items() if not v]} — 저장 안 함")
        clicked = True
        res, _ = pw.commit_save(tid, it, {"edText": st.get("edText")})
        if res.get("state") == "not-clicked":
            clicked = False
            pw.cancel_layer(tid)
            raise Stop(GATE, f"클릭 직전 재확인 실패 {json.dumps(res.get('pre', {}).get('chk'), ensure_ascii=False)}")
        if res.get("state") == "captcha":
            lock.touch()
            rc = pw.chacap_relay(tid, f"고지 /{pid} {title}")
            lock.touch()
            if rc != 0:
                raise Stop(CAPTCHA, f"CAPTCHA 중계 rc={rc}")
            pw.wait_left_editor(tid)
            res["state"] = "navigated"
        if res.get("state") != "navigated":
            raise Stop(UNVERIFIED, f"저장 결과 불명({res.get('state')})")
        clicked = False
        after = {}
        for _ in range(4):
            time.sleep(3)
            after = public_state(pid)
            if after["top"]:
                break
        log(f"  확인: {json.dumps(after, ensure_ascii=False)}")
        if not after["top"] or after["coupang"] < before["coupang"] or after["imgs"] < before["imgs"]:
            raise Stop(UNVERIFIED, f"저장 뒤 확인 실패 전 {before} 후 {after}")
        with DONE.open("a", encoding="utf-8") as f:
            f.write(pid + "\n")
    except Stop as exc:
        code = exc.code
        log(f"✗ /{pid} [{exc.code}] {exc.msg}")
        with FAIL.open("a", encoding="utf-8") as f:
            f.write(f"{pid}\t{exc.code}\t{exc.msg[:120]}\n")
    except Exception as exc:
        import traceback
        code = UNVERIFIED if clicked else GATE
        log(f"✗ /{pid} 예외: " + "".join(traceback.format_exception(exc))[-600:])
        with FAIL.open("a", encoding="utf-8") as f:
            f.write(f"{pid}\t{code}\t예외\n")
    finally:
        if tid:
            try:
                pw.autosave_restore(tid, None)
            except Stop:
                pass
            pw.close_tab(tid)
        lock.release()
    return code


def main() -> int:
    ids = [a.strip("/") for a in sys.argv[1:] if a.strip("/").isdigit()]
    done = set(DONE.read_text().split()) if DONE.exists() else set()
    last, n_ok = OK, 0
    for pid in ids:
        if pid in done:
            continue
        rc = edit_one(pid)
        print(f"{'OK' if rc == OK else 'FAIL'}\t/{pid}\trc={rc}", flush=True)
        if rc == OK:
            n_ok += 1
        else:
            last = rc
            if rc in (LOGIN, ASIDE_DOWN):
                break               # 로그인·Aside 가 죽었으면 나머지도 다 실패한다 — 멈춘다
    pw.prune_shots(last == OK)
    print(f"END ok={n_ok} last_rc={last}", flush=True)
    return last


if __name__ == "__main__":
    sys.exit(main())
