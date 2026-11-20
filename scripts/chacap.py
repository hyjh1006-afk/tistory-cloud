"""CHACAP — 티스토리 DKAPTCHA 를 대표님 폰(텔레그램)으로 중계한다.

  ⚠️ 이 도구는 CAPTCHA 를 「풀지」 않는다. 답을 추측·인식하는 코드는 없고 넣지도 않는다.
     하는 일은 ① 캡챠 화면을 찍어 텔레그램으로 보내고 ② 대표님이 보낸 답장 글자를
     ③ 그대로 입력칸에 옮겨 적는 것뿐이다. 답장이 없으면 아무것도 입력하지 않는다.

사용 (진입점은 scripts/chacap.sh):
  chacap.sh setup                    봇 토큰 확인 → 대표님 채팅 찾기 → 시험 메시지
  chacap.sh ping                     왕복 시험: 메시지 보내고 답장을 받아 되돌려 준다
  chacap.sh relay --tid <targetId>   그 탭의 캡챠를 중계 (publish_waiting.py 가 부른다)
  chacap.sh relay --match <정규식>    URL 이 맞는 탭의 캡챠를 중계 (cedar_post.sh 가 부른다)

relay 종료 코드
  0  대표님 답을 넣었고 캡챠가 사라짐(또는 페이지 이동)
  3  답장 없음(시간 초과) 또는 대표님이 「패스」
  4  중계 불가 — 텔레그램 설정 없음 / 캡챠 iframe·입력칸 못 찾음 (화면은 보냈음)
  2  Aside 오류

비밀값: 봇 토큰은 키체인(서비스 chacap-telegram, 계정 bot)에만 있다. 이 파일·로그에 찍지 않는다.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tg_inbox  # noqa: E402  공용 텔레그램 일지(맛집 질문과 봇을 같이 씀)

ASIDE = os.path.expanduser("~/.local/bin/aside")
KC_SERVICE = "chacap-telegram"
ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"chacap_{datetime.now():%Y%m%d_%H%M%S}.log"
IFR = 'iframe[src*="dkaptcha"]'
PASS_WORDS = {"패스", "pass", "/pass", "취소", "/cancel", "스킵", "skip"}
NEW_WORDS = {"새로", "새로고침", "/new", "new", "다시"}

OK, ASIDE_ERR, NO_ANSWER, CANT = 0, 2, 3, 4


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── 키체인 ───────────────────────────────────────────────────────────────
def kc_get(account: str) -> str | None:
    p = subprocess.run(["security", "find-generic-password", "-s", KC_SERVICE, "-a", account, "-w"],
                       capture_output=True, text=True)
    v = (p.stdout or "").strip()
    return v or None


def kc_set(account: str, value: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-s", KC_SERVICE, "-a", account, "-w", value],
                   capture_output=True, check=True)


# ── 텔레그램 ─────────────────────────────────────────────────────────────
class Tg:
    def __init__(self) -> None:
        tok = kc_get("bot")
        if not tok:
            raise SystemExit("키체인에 봇 토큰이 없습니다 (서비스 chacap-telegram, 계정 bot) — AGENTS.md 「CHACAP」 절 참고")
        self._base = f"https://api.telegram.org/bot{tok}/"
        self.chat = kc_get("chat")

    def call(self, method: str, params: dict | None = None, timeout: int = 30) -> dict:
        data = urllib.parse.urlencode(params or {}).encode()
        req = urllib.request.Request(self._base + method, data=data)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                res = json.loads(r.read())
        except urllib.error.HTTPError as e:  # 오류 본문엔 토큰이 없다
            res = json.loads(e.read() or b"{}")
        if not res.get("ok"):
            raise RuntimeError(f"텔레그램 {method} 실패: {res.get('description')}")
        if method == "getUpdates":
            # 맛집 질문 답장과 봇을 같이 쓴다 — 확인 처리로 사라지기 전에 공용 일지에 적어 둔다(scripts/tg_inbox.py)
            tg_inbox.journal(res["result"], self.chat)
        return res["result"]

    def send(self, text: str) -> dict:
        return self.call("sendMessage", {"chat_id": self.chat, "text": text})

    def photo(self, jpg: bytes, caption: str) -> dict:
        b = uuid.uuid4().hex
        parts = []
        for k, v in (("chat_id", str(self.chat)), ("caption", caption)):
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="captcha.jpg"\r\n'
                     f'Content-Type: image/jpeg\r\n\r\n'.encode() + jpg + b"\r\n")
        parts.append(f"--{b}--\r\n".encode())
        req = urllib.request.Request(self._base + "sendPhoto", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read())
        if not res.get("ok"):
            raise RuntimeError(f"텔레그램 sendPhoto 실패: {res.get('description')}")
        return res["result"]

    def drain(self) -> int:
        """지금까지 쌓인 메시지는 답으로 쓰지 않는다 — 다음에 읽을 offset 을 돌려준다."""
        # offset -1 은 마지막 1건만 돌려주고 나머지를 버린다 → 쌓인 걸 전부 받아 일지에 남긴 뒤 그 다음부터
        last = None
        for _ in range(20):
            ups = self.call("getUpdates", {"timeout": 0} if last is None else {"offset": last + 1, "timeout": 0})
            if not ups:
                break
            last = ups[-1]["update_id"]
        return (last + 1) if last is not None else 0

    def wait_text(self, offset: int, deadline: float) -> tuple[str | None, int]:
        """대표님 채팅에서 온 다음 글자 메시지. 다른 채팅에서 온 건 무시한다."""
        while time.time() < deadline:
            wait = int(max(1, min(50, deadline - time.time())))
            try:
                ups = self.call("getUpdates", {"offset": offset, "timeout": wait,
                                               "allowed_updates": json.dumps(["message"])}, timeout=wait + 15)
            except Exception as exc:  # 네트워크 끊김 — 잠깐 쉬고 다시
                log(f"  · getUpdates 오류: {exc}")
                time.sleep(5)
                continue
            for u in ups:
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                if str((m.get("chat") or {}).get("id")) != str(self.chat):
                    continue
                if m.get("text") and not tg_inbox.is_food_reply(m):   # 맛집 질문에 단 답장은 캡챠 답이 아니다
                    tg_inbox.mark_used(u["update_id"], "chacap")
                    return m["text"].strip(), offset
        return None, offset


# ── Aside ────────────────────────────────────────────────────────────────
def repl(body: str, timeout: int = 110) -> tuple[dict, list[str]]:
    code = (
        "const __out = await (async () => {\n" + body + "\n})()"
        ".catch(e => ({error: String((e && e.stack) || e).slice(0, 500)}));\n"
        "console.log('RESULT=' + JSON.stringify(__out));"
    )
    try:
        p = subprocess.run([ASIDE, "repl", code], cwd="/tmp", capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "aside repl 시간 초과"}, []
    out = (p.stdout or "") + (p.stderr or "")
    res, shots = None, []
    for line in out.splitlines():
        if line.startswith("RESULT="):
            res = json.loads(line[7:])
        elif line.startswith("SHOT="):
            shots.append(line[5:])
    return (res if res is not None else {"error": "aside 응답 없음: " + out.strip()[-200:]}), shots


def attach_js(tid: str | None, match: str | None) -> str:
    return (
        f"const TID = {json.dumps(tid)}, RE = {json.dumps(match)};\n"
        "const __t = (await listBrowserTabs()).filter(x => TID ? x.targetId === TID : new RegExp(RE).test(x.url));\n"
        "if (!__t.length) return {error: 'notab'};\n"
        "const P = await attachBrowserTab(__t[__t.length - 1].targetId);\n"
        f"const IFR = {json.dumps(IFR)};\n"
    )


def capture(tid, match) -> tuple[dict, bytes | None]:
    """캡챠 iframe 만 찍는다. iframe 이 없으면 화면 전체(대표님이 직접 판단하시게)."""
    body = attach_js(tid, match) + """
const ifr = P.locator(IFR).first();
const found = await ifr.count() > 0;
const visible = found ? await ifr.isVisible().catch(() => false) : false;
let text = '', inputs = 0, shot = null;
if (visible) {
  try { await ifr.scrollIntoViewIfNeeded({timeout: 3000}); } catch (e) {}
  try { shot = await ifr.screenshot({type: 'jpeg', quality: 85}); } catch (e) {}
  const fl = P.frameLocator(IFR).first();
  try { text = (await fl.locator('body').innerText({timeout: 5000})).replace(/\\s+/g, ' ').slice(0, 300); } catch (e) {}
  try { inputs = await fl.locator('input:not([type=hidden]):not([type=checkbox]):not([type=radio])').count(); } catch (e) {}
}
if (!shot) shot = await P.screenshot({type: 'jpeg', quality: 70});
console.log('SHOT=' + shot.toString('base64'));
return {found, visible, text, inputs, url: P.url()};
"""
    res, shots = repl(body)
    return res, (base64.b64decode(shots[-1]) if shots else None)


def type_answer(tid, match, answer: str) -> dict:
    """대표님 답장 글자를 그대로 입력칸에 넣고 확인을 누른 뒤, 캡챠가 사라졌는지 본다."""
    body = attach_js(tid, match) + f"""
const ANS = {json.dumps(answer, ensure_ascii=False)};
const fl = P.frameLocator(IFR).first();
const inp = fl.locator('input[placeholder*="정답"], input[type=text], input:not([type])').first();
await inp.fill(ANS, {{timeout: 8000}});
const typed = await inp.inputValue().catch(() => null);
if (typed !== ANS) return {{filled: false, typed}};
let how = 'enter';
// 2026-11-20 실측: DKAPTCHA 제출 버튼은 #btn_dkaptcha_submit 「답변 제출」이고 Enter 로는 제출되지 않는다.
// (전엔 문구를 「제출」로 딱 맞춰 찾다가 못 찾고 Enter 만 눌러, 맞는 답도 매번 「실패」로 끝났다)
let btn = fl.locator('#btn_dkaptcha_submit, .btn_submit_dkaptcha').first();
if (!(await btn.count())) btn = fl.locator('button, a[role=button], input[type=submit]').filter({{hasText: /(답변\\s*제출|확인|입력|제출|완료)/}}).first();
// 11/20 2차 실측: 실물에서 locator.click 이 실패하면 조용히 Enter 로 빠졌다(Enter 는 제출이 안 된다) → 실패 이유를 남기고 DOM click 으로 한 번 더
let clickErr = '';
if (await btn.count()) {{
  try {{ await btn.click({{timeout: 4000}}); how = 'button'; }}
  catch (e) {{
    clickErr = String(e).slice(0, 160);
    try {{ await btn.evaluate(b => b.click()); how = 'dom-click'; }}
    catch (e2) {{ clickErr += ' / ' + String(e2).slice(0, 120); await inp.press('Enter'); }}
  }}
}} else await inp.press('Enter');
const u0 = P.url();
let after = 'still';
for (let i = 0; i < 30; i++) {{   // 맞혀도 저장 요청이 끝나야 캡챠가 닫힌다 — 넉넉히 22초
  await sleep(750);
  if (P.url() !== u0) {{ after = 'navigated'; break; }}
  const vis = await P.locator(IFR).first().isVisible().catch(() => false);
  if (!vis) {{ after = 'gone'; break; }}
}}
let msg = '';
if (after === 'still') {{ try {{ msg = (await fl.locator('body').innerText({{timeout: 3000}})).replace(/\\s+/g, ' ').slice(0, 160); }} catch (e) {{}} }}
return {{filled: true, how, after, msg, clickErr}};
"""
    return repl(body)[0]


def refresh(tid, match) -> None:
    body = attach_js(tid, match) + """
const fl = P.frameLocator(IFR).first();
const b = fl.locator('button, a').filter({hasText: /새로|다른 문제|refresh/i}).first();
if (await b.count()) { await b.click({timeout: 5000}); await sleep(1500); return {ok: true}; }
const b2 = fl.locator('[aria-label*="새로"], [title*="새로"], [class*=refresh]').first();
if (await b2.count()) { await b2.click({timeout: 5000}); await sleep(1500); return {ok: true}; }
return {ok: false};
"""
    log(f"  새 문제 요청: {repl(body)[0]}")


# ── 명령 ────────────────────────────────────────────────────────────────
def cmd_setup(_a) -> int:
    tg = Tg()
    me = tg.call("getMe")
    log(f"봇 확인: @{me.get('username')}")
    ups = tg.call("getUpdates", {"timeout": 0})
    chats = [u["message"]["chat"] for u in ups if u.get("message", {}).get("chat", {}).get("type") == "private"]
    if not chats:
        log(f"✗ 봇에게 온 메시지가 없습니다. 텔레그램에서 @{me.get('username')} 에게 /start 를 보내고 다시 실행하세요.")
        return CANT
    chat = chats[-1]
    kc_set("chat", str(chat["id"]))
    tg.chat = str(chat["id"])
    tg.send("✅ CHACAP 연결됨. 티스토리에 CAPTCHA 가 뜨면 화면을 여기로 보냅니다.\n"
            "사진에 답장으로 정답만 보내 주세요. 「새로」= 다른 문제, 「패스」= 이번 건 건너뛰기.")
    log(f"✓ 대표님 채팅 저장 (이름 {chat.get('first_name', '')}) — 텔레그램에 시험 메시지 보냄")
    return OK


def cmd_ping(a) -> int:
    tg = Tg()
    if not tg.chat:
        log("✗ 채팅이 아직 없습니다 — setup 먼저")
        return CANT
    off = tg.drain()
    tg.send("🧪 CHACAP 왕복 시험 — 아무 글자나 답장으로 보내 주세요.")
    txt, _ = tg.wait_text(off, time.time() + a.wait_min * 60)
    if txt is None:
        log("✗ 시간 안에 답장이 없었습니다")
        return NO_ANSWER
    tg.send(f"받은 답: 「{txt}」 — 실제 상황이면 이 글자를 입력칸에 그대로 넣습니다.")
    log(f"✓ 왕복 성공 (받은 글자 {len(txt)}자)")
    return OK


def cmd_relay(a) -> int:
    if not (a.tid or a.match):
        log("✗ --tid 또는 --match 가 필요합니다")
        return CANT
    try:
        tg = Tg()
    except SystemExit as exc:
        log(f"✗ {exc}")
        return CANT
    if not tg.chat:
        log("✗ 텔레그램 채팅이 설정 안 됨 — chacap.sh setup")
        return CANT
    label = a.label or "티스토리"
    off = tg.drain()
    deadline_total = time.time() + a.wait_min * 60
    for rnd in range(1, a.rounds + 1):
        info, jpg = capture(a.tid, a.match)
        if info.get("error"):
            log(f"✗ 화면 캡처 실패: {info['error']}")
            return ASIDE_ERR if info["error"] != "notab" else CANT
        log(f"[{rnd}회] 캡챠 iframe={info.get('found')}/{info.get('visible')} 입력칸 {info.get('inputs')}개 · 문구: {info.get('text', '')[:80]}")
        relayable = info.get("visible") and (info.get("inputs") or 0) > 0
        if not relayable:
            if jpg:
                tg.photo(jpg, f"⚠️ {label} — 캡챠로 멈췄는데 입력칸을 못 찾았습니다. 맥에서 직접 풀어 주세요.")
            log("✗ 입력칸이 있는 DKAPTCHA 가 아님 — 화면만 보냄")
            return CANT
        if rnd == 1:
            cap = f"🔐 {label} CAPTCHA\n이 사진에 답장으로 정답만 보내 주세요.\n「새로」 다른 문제 · 「패스」 건너뛰기 ({a.wait_min}분 대기)"
        else:
            cap = "↩️ 통과가 안 됐습니다(틀렸거나 새 문제). 다시 보고 답해 주세요."
        if jpg:
            tg.photo(jpg, cap)
        else:
            tg.send(cap + "\n(화면 캡처 실패 — 맥에서 확인해 주세요)")
        while True:
            ans, off = tg.wait_text(off, deadline_total)
            if ans is None:
                tg.send(f"⌛ {a.wait_min}분 동안 답이 없어 이번 건은 넘깁니다. 편집기 탭은 열어 둡니다.")
                log("✗ 답장 없음 — 시간 초과")
                return NO_ANSWER
            if ans.lower() in PASS_WORDS:
                tg.send("⏭ 건너뜁니다. 편집기 탭은 열어 둡니다.")
                log("· 대표님 패스")
                return NO_ANSWER
            if ans in NEW_WORDS:
                refresh(a.tid, a.match)
                info, jpg = capture(a.tid, a.match)
                if jpg:
                    tg.photo(jpg, "🔄 새 문제입니다. 답장으로 정답을 보내 주세요.")
                continue
            break
        log(f"  답 받음 ({len(ans)}자) — 입력")
        r = type_answer(a.tid, a.match, ans)
        log(f"  입력 결과: {r}")
        if r.get("error") or not r.get("filled"):
            tg.send(f"⚠️ 입력칸에 넣지 못했습니다({str(r.get('error') or r.get('typed'))[:80]}). 맥에서 직접 넣어 주세요.")
            return CANT
        if r.get("after") in ("gone", "navigated"):
            tg.send("✅ 통과 — 발행을 이어 갑니다.")
            log("✓ 캡챠 통과")
            return OK
    tg.send(f"❌ {a.rounds}번 시도했는데 통과가 안 됐습니다. 맥에서 확인해 주세요.")
    return NO_ANSWER


HARNESS_FRAME = (
    "<!-- dkaptcha harness --><meta charset=utf-8><body style='font:16px sans-serif;padding:12px'>"
    "<p id=q>[CHACAP 시험] 아래 칸에 7 을 넣으면 통과</p>"
    # 실물 DKAPTCHA 그대로(11/20 실측): 입력칸 #inpDkaptcha, 「새로 풀기」, 제출은 #btn_dkaptcha_submit 「답변 제출」, Enter 로는 제출 안 됨
    "<input id=inpDkaptcha class=inp_dkaptcha style='font-size:16px'> <button type=button id=btn_dkaptcha_reset>새로 풀기</button>"
    " <button type=button id=btn_dkaptcha_submit class=btn_submit_dkaptcha>답변 제출</button>"
    "<script>document.getElementById('btn_dkaptcha_submit').onclick=()=>{"
    "if(document.querySelector('input').value==='7')parent.postMessage('chacap-ok','*');"
    "else document.getElementById('q').textContent='틀렸습니다 — 7 을 넣으세요'}</script>"
)


def harness_url() -> str:
    inner = "data:text/html;charset=utf-8," + urllib.parse.quote(HARNESS_FRAME)
    top = ("<meta charset=utf-8><title>CHACAP-TEST</title><h3>CHACAP-TEST 편집기 흉내</h3>"
           f"<iframe id=k src=\"{inner}\" width=380 height=200></iframe>"
           "<script>addEventListener('message',e=>{if(e.data==='chacap-ok')document.getElementById('k').remove()})</script>")
    return "data:text/html;charset=utf-8," + urllib.parse.quote(top)


def cmd_selftest(_a) -> int:
    """텔레그램 없이 Aside 쪽(캡처·입력·통과 판정)만 시험한다. 다른 출처 iframe 을 흉내낸 가짜 캡챠 페이지로."""
    aside_sh = os.path.expanduser("~/.claude/tools/screen/aside.sh")
    m = "CHACAP-TEST"

    def close_all() -> None:
        # repl 의 page.close() 는 남의 탭을 떼기만 하고 안 닫는다(2026-11-17 실측) — aside.sh 로 닫는다
        for _ in range(4):
            subprocess.run([aside_sh, "close", m], capture_output=True, timeout=30)

    close_all()  # 지난 시험 탭이 남아 있으면 그쪽에 붙어 조용히 틀린 답을 낸다
    subprocess.run([aside_sh, "open", harness_url()], capture_output=True, timeout=60)
    time.sleep(3)
    bad = 3
    try:
        info, jpg = capture(None, m)
        ok1 = bool(info.get("visible") and info.get("inputs") and jpg and len(jpg) > 2000)
        log(f"캡처: {'O' if ok1 else 'X'} {({k: v for k, v in info.items() if k != 'url'})} 사진 {len(jpg or b'')}바이트")
        (LOG_DIR / "chacap_selftest.jpg").write_bytes(jpg or b"")
        r1 = type_answer(None, m, "3")
        ok2 = r1.get("filled") and r1.get("after") == "still"
        log(f"틀린 답 → 남아 있어야 함: {'O' if ok2 else 'X'} {r1}")
        r2 = type_answer(None, m, "7")
        ok3 = r2.get("filled") and r2.get("after") == "gone"
        log(f"맞는 답 → 사라져야 함: {'O' if ok3 else 'X'} {r2}")
        bad = sum(not x for x in (ok1, ok2, ok3))
    finally:
        close_all()
    log("✓ selftest 통과" if not bad else f"✗ selftest 실패 {bad}건")
    return OK if not bad else CANT


def main() -> int:
    ap = argparse.ArgumentParser(prog="chacap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sub.add_parser("selftest")
    p = sub.add_parser("ping")
    p.add_argument("--wait-min", type=float, default=5)
    r = sub.add_parser("relay")
    r.add_argument("--tid")
    r.add_argument("--match")
    r.add_argument("--label")
    r.add_argument("--wait-min", type=float, default=float(os.environ.get("CHACAP_WAIT_MIN", "15")))
    r.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    try:
        return {"setup": cmd_setup, "ping": cmd_ping, "relay": cmd_relay, "selftest": cmd_selftest}[a.cmd](a)
    except RuntimeError as exc:
        log(f"✗ {exc}")
        return CANT


if __name__ == "__main__":
    raise SystemExit(main())
