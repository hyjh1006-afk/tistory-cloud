"""레딧 수집 — Aside 브라우저 화면에서 읽기 (2026-11-23~).

레딧이 RSS(.rss)를 없앴다: 브라우저 안에서 같은 주소를 불러도 404, .json 은 403. 맥·프록시 모두 같음.
게시판 화면(/r/<sub>/new/)은 Aside 에서 정상으로 열리고 `shreddit-post` 의 [slot=text-body] 에 본문이 끝까지 들어 있다
(nosleep 3만 자 글도 상세 페이지와 길이가 같음 — 실측). 그래서 화면을 몇 번 내려 글을 모으고 탭은 닫는다.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from .duplicates import normalize_reddit_url

ASIDE = os.path.expanduser("~/.local/bin/aside")

_JS = r"""
const __u = %(url)s;
const __t = await openTab(__u);
let __res;
try {
  await sleep(4000);
  for (let i = 0; i < %(scrolls)d; i++) {
    await __t.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(1800);
  }
  __res = await __t.evaluate(() => [...document.querySelectorAll('shreddit-post')].map(p => ({
    id: p.getAttribute('id') || '',
    title: p.getAttribute('post-title') || '',
    permalink: p.getAttribute('permalink') || '',
    author: p.getAttribute('author') || '',
    created: p.getAttribute('created-timestamp') || '',
    score: Number(p.getAttribute('score') || 0),
    comments: Number(p.getAttribute('comment-count') || 0),
    type: p.getAttribute('post-type') || '',
    nsfw: p.hasAttribute('nsfw'),
    stickied: p.hasAttribute('stickied') || p.hasAttribute('pinned'),
    body: ((p.querySelector('[slot=text-body]') || {}).innerText || '').trim(),
  })));
} catch (e) {
  __res = {error: String(e).slice(0, 300)};
}
await closeTab(__t);
console.log('RESULT=' + JSON.stringify(__res));
"""


def fetch_via_aside(subreddit: str, sort: str = "new", *, limit: int = 150, scrolls: int = 4,
                    logger: Any = None) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/{sort or 'new'}/"
    code = _JS % {"url": json.dumps(url), "scrolls": scrolls}
    try:
        p = subprocess.run([ASIDE, "repl", code], cwd="/tmp", capture_output=True, text=True, timeout=110)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Aside 수집 실패: {type(exc).__name__}") from exc
    out = (p.stdout or "") + (p.stderr or "")
    raw = None
    for line in out.splitlines():
        if line.startswith("RESULT="):
            raw = json.loads(line[7:])
    if raw is None:
        raise RuntimeError("Aside 수집 결과 없음: " + out.strip()[-200:])
    if isinstance(raw, dict):
        raise RuntimeError("Aside 수집 오류: " + str(raw.get("error")))

    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in raw:
        pid = (r.get("id") or "").lower()
        pid = pid[3:] if pid.startswith("t3_") else pid
        if not pid or pid in seen or not r.get("permalink"):
            continue
        seen.add(pid)
        created = ""
        try:
            created = datetime.fromisoformat(r["created"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        posts.append({
            "post_id": pid,
            "title": r.get("title", "").strip(),
            "selftext": r.get("body", ""),
            "url": normalize_reddit_url("https://www.reddit.com" + r["permalink"]),
            "author": r.get("author") or "unknown",
            "created_at": created,
            "score": r.get("score", 0),
            "num_comments": r.get("comments", 0),
            "is_self": r.get("type") == "text",
            "over_18": bool(r.get("nsfw")),
            "removed_by_category": None,
            "stickied": bool(r.get("stickied")),
            "locked": False,
        })
        if len(posts) >= limit:
            break
    if logger:
        logger.info("Aside 화면 수집: %s (%s건)", url, len(posts))
    return posts
