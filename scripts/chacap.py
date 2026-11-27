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
        with urllib.request.urlopen(req, timeout=150) as r:
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
// 11/20 실측: 저장 직후엔 캡챠 iframe 이 아직 안 그려져 화면 전체(흐린 편집기)를 보냈다 — 대표님이 풀 수 없는 사진.
// → iframe 이 보이고 안에 문제 글자가 뜰 때까지 최대 15초 기다린 뒤 찍는다.
let found = false, visible = false;
for (let i = 0; i < 30; i++) {
  found = await ifr.count() > 0;
  visible = found ? await ifr.isVisible().catch(() => false) : false;
  if (visible) {
    const t = await P.frameLocator(IFR).first().locator('body').innerText({timeout: 1500}).catch(() => '');
    if (/입력해주세요|빈칸|DKAPTCHA/.test(t)) break;
  }
  await sleep(500);
}
let text = '', inputs = 0, shot = null, box = null, dpr = 1;
if (visible) {
  try { await ifr.scrollIntoViewIfNeeded({timeout: 3000}); } catch (e) {}
  // 11/20 실측: Aside 에선 요소 스크린샷·clip 이 위치를 무시하고 화면 왼쪽 위를 잘라 준다(흐린 편집기 사진의 정체).
  // → 화면 전체를 찍고(이건 정확하다) 상자 좌표·배율을 같이 넘겨 파이썬에서 자른다.
  try { box = await ifr.boundingBox(); dpr = await P.evaluate(() => window.devicePixelRatio || 1); } catch (e) {}
  try { shot = await P.screenshot({type: 'jpeg', quality: 88}); } catch (e) {}
  const fl = P.frameLocator(IFR).first();
  try { text = (await fl.locator('body').innerText({timeout: 5000})).replace(/\\s+/g, ' ').slice(0, 300); } catch (e) {}
  try { inputs = await fl.locator('input:not([type=hidden]):not([type=checkbox]):not([type=radio])').count(); } catch (e) {}
}
if (!shot) shot = await P.screenshot({type: 'jpeg', quality: 70});
console.log('SHOT=' + shot.toString('base64'));
return {found, visible, text, inputs, url: P.url(), box, dpr};
"""
    res, shots = repl(body)
    jpg = base64.b64decode(shots[-1]) if shots else None
    if jpg and res.get("box"):
        jpg = crop_jpg(jpg, res["box"], res.get("dpr") or 1) or jpg
    return res, jpg


def crop_jpg(jpg: bytes, box: dict, dpr: float, pad: int = 8) -> bytes | None:
    """sips 로 캡챠 상자만 잘라 낸다(레포 .venv 엔 PIL 이 없다). 실패하면 None → 화면 전체를 보낸다."""
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="chacap_"))
    src, out = d / "full.jpg", d / "crop.jpg"
    try:
        src.write_bytes(jpg)
        x, y = max(0, int((box["x"] - pad) * dpr)), max(0, int((box["y"] - pad) * dpr))
        w, h = int((box["width"] + 2 * pad) * dpr), int((box["height"] + 2 * pad) * dpr)
        r = subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", str(y), str(x), str(src), "--out", str(out)],
                           capture_output=True, text=True, timeout=30)
        return out.read_bytes() if r.returncode == 0 and out.exists() else None
    except Exception:
        return None
    finally:
        for f in (src, out):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            d.rmdir()
        except OSError:
            pass


def type_answer(tid, match, answer: str) -> dict:
    """대표님 답장 글자를 그대로 입력칸에 넣고 확인을 누른 뒤, 캡챠가 사라졌는지 본다."""
    body = attach_js(tid, match) + f"""
const ANS = {json.dumps(answer, ensure_ascii=False)};
const fl = P.frameLocator(IFR).first();
const inp = fl.locator('input[placeholder*="정답"], input[type=text], input:not([type])').first();
await inp.fill(ANS, {{timeout: 8000}});
const typed = await inp.inputValue().catch(() => null);
if (typed !== ANS) return {{filled: false, typed}};
// 11/20 3차 실측: DKAPTCHA 는 jQuery keyup 이 와야 「답변 제출」 disabled 를 푼다. fill·한글 입력은 keyup 을 안 낸다
// → 버튼이 꺼진 채 클릭 실패 → Enter(무효) → 맞는 답도 「통과 안 됨」. keyup·change 를 직접 쏘고 버튼이 켜질 때까지 본다.
// 4차 실측: Playwright dispatchEvent('keyup') 은 keyCode 가 없어 안 먹고, 진짜 키 입력(End)이 먹는다 — 커서만 끝으로 옮기는 무해한 키
try {{ await inp.press('End'); }} catch (e) {{}}
for (const ev of ['change']) {{ try {{ await inp.dispatchEvent(ev); }} catch (e) {{}} }}
const subBtn = fl.locator('#btn_dkaptcha_submit, .btn_submit_dkaptcha').first();
let enabled = null;
if (await subBtn.count()) {{ for (let i = 0; i < 12; i++) {{ enabled = await subBtn.isEnabled().catch(() => null); if (enabled) break; await sleep(250); }} }}
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
return {{filled: true, how, after, msg, clickErr, enabled}};
"""
    return repl(body)[0]


def reload_frame(tid, match) -> dict:
    """11/27 실측: 캡챠 iframe 이 「Bad Request」만 띄우고 입력칸이 없었다(문제를 못 받아 옴).
    iframe 주소를 다시 불러 문제를 새로 받는다 — 사람이 풀 문제를 다시 받아 오는 것뿐, 우회가 아니다."""
    body = attach_js(tid, match) + """
const src = await P.evaluate((sel) => {
  const f = document.querySelector(sel);
  if (!f) return '';
  const s = f.src; f.src = 'about:blank'; setTimeout(() => { f.src = s; }, 300);
  return s;
}, IFR);
if (!src) return {ok: false};
await sleep(4000);
return {ok: true, src: src.replace(/([?&][^=]+=)[^&]{12,}/g, '$1…').slice(0, 200)};
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


def safe(fn, *args):
    """텔레그램 보내기가 느려 응답 대기 시간이 넘어도(11/20 실측: sendPhoto 60초 초과로 중계가 통째로 죽음) 죽지 않는다.
    대개 메시지는 이미 갔다 — 기록만 남기고 답을 계속 기다린다."""
    for attempt in (1, 2):
        try:
            return fn(*args)
        except Exception as exc:
            log(f"  · 텔레그램 보내기 {attempt}회 실패: {str(exc)[:120]}")
            if "timed out" in str(exc):     # 시간 초과면 이미 갔을 공산이 크다 — 두 번 보내지 않는다
                return None
            time.sleep(3)
    return None


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
    try:
        off = tg.drain()
    except Exception as exc:          # 네트워크가 느려도 중계는 이어 간다(지난 메시지를 답으로 오인할 위험만 조금 생긴다)
        log(f"  · drain 실패: {str(exc)[:100]}")
        off = 0
    deadline_total = time.time() + a.wait_min * 60
    for rnd in range(1, a.rounds + 1):
        info, jpg = capture(a.tid, a.match)
        if info.get("error"):
            log(f"✗ 화면 캡처 실패: {info['error']}")
            return ASIDE_ERR if info["error"] != "notab" else CANT
        log(f"[{rnd}회] 캡챠 iframe={info.get('found')}/{info.get('visible')} 입력칸 {info.get('inputs')}개 · 문구: {info.get('text', '')[:80]}")
        relayable = info.get("visible") and (info.get("inputs") or 0) > 0
        for k in range(2):   # 문제 창이 「Bad Request」 등으로 빈 채 뜨면 두 번까지 다시 불러 본다
            if relayable or not info.get("visible"):
                break
            log(f"  · 입력칸 없음 — 캡챠 창 다시 불러옴({k + 1}회): {reload_frame(a.tid, a.match)}")
            info, jpg = capture(a.tid, a.match)
            log(f"  · 다시 본 캡챠: 입력칸 {info.get('inputs')}개 · 문구: {info.get('text', '')[:80]}")
            relayable = info.get("visible") and (info.get("inputs") or 0) > 0
        if not relayable:
            if jpg:
                safe(tg.photo, jpg, f"⚠️ {label} — 캡챠로 멈췄는데 입력칸을 못 찾았습니다. 맥에서 직접 풀어 주세요.")
            log("✗ 입력칸이 있는 DKAPTCHA 가 아님 — 화면만 보냄")
            return CANT
        if rnd == 1:
            cap = f"🔐 {label} CAPTCHA\n이 사진에 답장으로 정답만 보내 주세요.\n「새로」 다른 문제 · 「패스」 건너뛰기 ({a.wait_min}분 대기)"
        # 문제 글자도 같이 적는다 — 사진이 흐리거나 잘려도 무엇을 찾는지 알 수 있게
        qm = re.search(r"(지도[^.]*?입력해주세요)\s*(?:문제\s*)?(.*?)\s*정답을 입력", info.get("text", ""))
        if qm:
            cap += f"\n\n❓ {qm.group(1)}" + (f"\n👉 {qm.group(2).replace('빈칸', ' ___ ')}" if qm.group(2) else "")
        else:
            cap = "↩️ 통과가 안 됐습니다(틀렸거나 새 문제). 다시 보고 답해 주세요."
        if jpg:
            safe(tg.photo, jpg, cap)
        else:
            safe(tg.send, cap + "\n(화면 캡처 실패 — 맥에서 확인해 주세요)")
        while True:
            ans, off = tg.wait_text(off, deadline_total)
            if ans is None:
                safe(tg.send, f"⌛ {a.wait_min}분 동안 답이 없어 이번 건은 넘깁니다. 편집기 탭은 열어 둡니다.")
                log("✗ 답장 없음 — 시간 초과")
                return NO_ANSWER
            if ans.lower() in PASS_WORDS:
                safe(tg.send, "⏭ 건너뜁니다. 편집기 탭은 열어 둡니다.")
                log("· 대표님 패스")
                return NO_ANSWER
            if ans in NEW_WORDS:
                refresh(a.tid, a.match)
                info, jpg = capture(a.tid, a.match)
                if jpg:
                    safe(tg.photo, jpg, "🔄 새 문제입니다. 답장으로 정답을 보내 주세요.")
                continue
            break
        log(f"  답 받음 ({len(ans)}자) — 입력")
        r = type_answer(a.tid, a.match, ans)
        log(f"  입력 결과: {r}")
        if r.get("error") or not r.get("filled"):
            safe(tg.send, f"⚠️ 입력칸에 넣지 못했습니다({str(r.get('error') or r.get('typed'))[:80]}). 맥에서 직접 넣어 주세요.")
            return CANT
        if r.get("after") in ("gone", "navigated"):
            safe(tg.send, "✅ 통과 — 발행을 이어 갑니다.")
            log("✓ 캡챠 통과")
            return OK
    safe(tg.send, f"❌ {a.rounds}번 시도했는데 통과가 안 됐습니다. 맥에서 확인해 주세요.")
    return NO_ANSWER


HARNESS_FRAME = (
    "<!-- dkaptcha harness --><meta charset=utf-8><body style='font:16px sans-serif;padding:12px'>"
    "<p id=q>[CHACAP 시험] 아래 칸에 7 을 넣으면 통과</p>"
    # 실물 DKAPTCHA 그대로(11/20 실측): 입력칸 #inpDkaptcha, 「새로 풀기」, 제출은 #btn_dkaptcha_submit 「답변 제출」, Enter 로는 제출 안 됨
    "<input id=inpDkaptcha class=inp_dkaptcha style='font-size:16px'> <button type=button id=btn_dkaptcha_reset>새로 풀기</button>"
    " <button type=button id=btn_dkaptcha_submit class=btn_submit_dkaptcha>답변 제출</button>"
    # 실물처럼: 「답변 제출」은 disabled 로 시작하고 keyup 이 와야 켜진다(11/20 3차 실측)
    "<script>const SB=document.getElementById('btn_dkaptcha_submit');SB.disabled=true;"
    "document.getElementById('inpDkaptcha').addEventListener('keyup',e=>{if(!e.keyCode)return;SB.disabled=!document.getElementById('inpDkaptcha').value});"
    "SB.onclick=()=>{"
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
