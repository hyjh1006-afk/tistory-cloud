# -*- coding: utf-8 -*-
"""대표님 텔레그램 봇(@oddo_chacap_bot) 공용 창구 — CHACAP(캡챠 중계)과 맛집 질문이 같은 봇을 나눠 쓴다.

왜 일지가 필요한가: 텔레그램 getUpdates 는 offset 으로 「확인」한 메시지를 서버에서 지운다.
CHACAP 이 캡챠 답을 기다리며 확인 처리하면, 그 사이 온 맛집 답이 사라진다(반대도 마찬가지).
→ 누가 getUpdates 로 무엇을 받든 **먼저 일지(JOURNAL)에 적는다.** 맛집 쪽은 확인 처리를 하지 않고(peek) 일지로 읽는다.
서버는 확인 안 된 메시지를 24시간 보관한다 — 그 안에 누군가 한 번은 읽어 일지에 남겨야 한다.

비밀: 봇 토큰·채팅 id 는 키체인(chacap-telegram / bot, chat). 일지는 레포 밖(공개 레포라서)에 둔다.
"""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

KC_SERVICE = "chacap-telegram"
JOURNAL = Path.home() / ".local/share/oddo-tg/inbox.jsonl"


def kc_get(account: str) -> str | None:
    p = subprocess.run(["security", "find-generic-password", "-s", KC_SERVICE, "-a", account, "-w"],
                       capture_output=True, text=True)
    return p.stdout.strip() or None if p.returncode == 0 else None


def journal(updates: list[dict], chat) -> None:
    """getUpdates 결과를 일지에 덧붙인다(같은 update_id 는 한 번만)."""
    if not updates:
        return
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    seen = {m["update_id"] for m in read_journal(raw=True)}
    with JOURNAL.open("a", encoding="utf-8") as f:
        for u in updates:
            m = u.get("message") or {}
            if u["update_id"] in seen or str((m.get("chat") or {}).get("id")) != str(chat):
                continue
            r = m.get("reply_to_message") or None
            f.write(json.dumps({
                "update_id": u["update_id"], "date": m.get("date"), "text": m.get("text"),
                "reply_to": ({"message_id": r.get("message_id"), "head": (r.get("text") or r.get("caption") or "")[:20]} if r else None),
            }, ensure_ascii=False) + "\n")


def mark_used(update_id: int, by: str) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"used": update_id, "by": by}) + "\n")


def read_journal(raw: bool = False) -> list[dict]:
    if not JOURNAL.exists():
        return []
    msgs, used = [], {}
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if "used" in o:
            used[o["used"]] = o["by"]
        else:
            msgs.append(o)
    if not raw:
        for m in msgs:
            if m["update_id"] in used:
                m["used_by"] = used[m["update_id"]]
    return msgs


def is_food_reply(msg: dict) -> bool:
    """맛집 질문(🍽 로 시작)에 단 답장 — CHACAP 은 이걸 캡챠 답으로 쓰지 않는다."""
    r = msg.get("reply_to_message") or {}
    return (r.get("text") or r.get("caption") or "").startswith("🍽")


class Tg:
    def __init__(self) -> None:
        tok = kc_get("bot")
        if not tok:
            raise SystemExit("키체인에 봇 토큰이 없습니다 (서비스 chacap-telegram, 계정 bot)")
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
            journal(res["result"], self.chat)
        return res["result"]

    def send(self, text: str) -> dict:
        return self.call("sendMessage", {"chat_id": self.chat, "text": text})

    def _multipart(self, method: str, fields: dict, files: list[tuple[str, str, bytes]]) -> dict:
        b = uuid.uuid4().hex
        parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
        for name, fname, data in files:
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                         f'Content-Type: image/jpeg\r\n\r\n'.encode() + data + b"\r\n")
        parts.append(f"--{b}--\r\n".encode())
        req = urllib.request.Request(self._base + method, data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read())
        if not res.get("ok"):
            raise RuntimeError(f"텔레그램 {method} 실패: {res.get('description')}")
        return res["result"]

    def photo(self, jpg: bytes, caption: str) -> dict:
        return self._multipart("sendPhoto", {"chat_id": str(self.chat), "caption": caption}, [("photo", "captcha.jpg", jpg)])

    def media_group(self, jpgs: list[bytes]) -> list[dict]:
        jpgs = jpgs[:10]
        if len(jpgs) == 1:
            return [self._multipart("sendPhoto", {"chat_id": str(self.chat)}, [("photo", "p0.jpg", jpgs[0])])]
        media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(jpgs))]
        return self._multipart("sendMediaGroup", {"chat_id": str(self.chat), "media": json.dumps(media)},
                               [(f"p{i}", f"p{i}.jpg", j) for i, j in enumerate(jpgs)])

    def peek(self) -> list[dict]:
        """확인 처리 없이 남아 있는 메시지를 읽어 일지에 적는다."""
        try:
            return self.call("getUpdates", {"timeout": 0, "allowed_updates": json.dumps(["message"])})
        except RuntimeError:     # CHACAP 이 동시에 기다리는 중(409) 등 — 다음에 다시
            return []
