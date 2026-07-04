"""클라우드 서버 IP가 Reddit에 직접 차단됐을 때 쓰는 프록시 폴백.

1순위 allorigins: 원본 Atom XML을 그대로 중계 → 기존 파서 재사용 (가끔 타임아웃, 재시도 필요)
2순위 rss2json: RSS→JSON 변환 서비스 (무료는 피드당 10개 제한 → 여러 피드 합침)
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import requests

from .duplicates import extract_post_id, normalize_reddit_url
from .reddit_rss import _SUBMITTED_TAIL_RE, _strip_html, parse_rss_posts

ALLORIGINS_URL = "https://api.allorigins.win/raw?url={target}"
RSS2JSON_URL = "https://api.rss2json.com/v1/api.json"


def fetch_via_proxies(
    urls: list[str],
    *,
    limit: int,
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]]:
    posts = _try_allorigins(urls, limit=limit, logger=logger)
    if posts:
        return posts
    return _try_rss2json(urls, limit=limit, logger=logger)


def _try_allorigins(
    urls: list[str], *, limit: int, logger: logging.Logger | None
) -> list[dict[str, Any]]:
    for url in urls[:2]:
        proxy_url = ALLORIGINS_URL.format(target=quote(url, safe=""))
        for attempt in range(2):
            try:
                response = requests.get(proxy_url, timeout=45)
                if response.status_code != 200:
                    continue
                batch = parse_rss_posts(response.text, limit=limit)
                if batch:
                    if logger:
                        logger.info("allorigins 프록시 수집 성공: %s (%s건)", url, len(batch))
                    return batch
            except (requests.RequestException, ValueError):
                continue
    return []


def _try_rss2json(
    urls: list[str], *, limit: int, logger: logging.Logger | None
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for url in urls:
        try:
            response = requests.get(RSS2JSON_URL, params={"rss_url": url}, timeout=30)
            data = response.json()
        except (requests.RequestException, ValueError):
            continue
        if data.get("status") != "ok":
            continue
        for item in data.get("items", []):
            post = _post_from_rss2json_item(item)
            if post and post["post_id"] not in merged:
                merged[post["post_id"]] = post
        if len(merged) >= limit:
            break

    posts = list(merged.values())
    if posts and logger:
        logger.info("rss2json 프록시 수집 성공 (%s건)", len(posts))
    return posts[:limit]


def _post_from_rss2json_item(item: dict[str, Any]) -> dict[str, Any] | None:
    link = str(item.get("link") or item.get("guid") or "").split("?")[0]
    if not link or "/comments/" not in link:
        return None
    link = normalize_reddit_url(link)
    post_id = (extract_post_id(link) or "").lower()
    if not post_id:
        return None

    html_body = str(item.get("content") or item.get("description") or "")
    had_markers = "<!-- SC_OFF -->" in html_body or "<!-- SC_ON -->" in html_body
    if "<!-- SC_OFF -->" in html_body:
        html_body = html_body.split("<!-- SC_OFF -->", 1)[1]
    if "<!-- SC_ON -->" in html_body:
        html_body = html_body.split("<!-- SC_ON -->", 1)[0]
    selftext = _strip_html(html_body)
    if not had_markers:
        selftext = _SUBMITTED_TAIL_RE.sub("", selftext).strip()

    author = str(item.get("author") or "").strip()
    for prefix in ("/u/", "u/"):
        if author.startswith(prefix):
            author = author[len(prefix):]
            break

    return {
        "post_id": post_id,
        "title": str(item.get("title") or "").strip(),
        "selftext": selftext,
        "url": link,
        "author": author or "unknown",
        "created_at": str(item.get("pubDate") or "").strip(),
        "score": 0,
        "num_comments": 0,
        "is_self": True,
        "over_18": False,
        "removed_by_category": None,
        "stickied": False,
        "locked": False,
    }
