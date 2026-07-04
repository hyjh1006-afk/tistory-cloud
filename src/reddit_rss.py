"""Reddit RSS 읽기 전용 수집."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

import requests

from .duplicates import extract_post_id, normalize_reddit_url

BLOCK_MARKERS = (
    "captcha",
    "log in",
    "login",
    "access denied",
    "blocked",
    "verify you are human",
    "rate limit",
    "forbidden",
)


def looks_like_feed(text: str) -> bool:
    head = (text or "").lstrip()[:2000].lower()
    return ("<feed" in head or "<rss" in head) and (
        "<entry" in (text or "").lower() or "<item" in (text or "").lower()
    )


def is_blocked_response(text: str, *, status_code: int | None = None) -> bool:
    if status_code in (401, 403, 429):
        return True
    # 정상 피드 XML이면 본문에 "login" 같은 단어가 있어도 차단이 아니다.
    if looks_like_feed(text):
        return False
    lowered = (text or "").lower()[:8000]
    return any(marker in lowered for marker in BLOCK_MARKERS)


def fetch_via_rss(url: str, *, user_agent: str, timeout: int = 25) -> str:
    # 헤더는 User-Agent만. 봇 UA에 브라우저용 Accept-Language 등을 섞으면
    # Reddit WAF가 위장 봇으로 판정해 429/403을 반환하는 것이 관측됨 (2026-07).
    response = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    if response.status_code == 403:
        raise requests.HTTPError("403 Blocked", response=response)
    response.raise_for_status()
    text = response.text
    if is_blocked_response(text, status_code=response.status_code):
        raise requests.HTTPError("blocked page", response=response)
    return text


def _strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_pubdate(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    # Atom(<published>)은 이미 ISO 8601 형식
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    # RSS 2.0(<pubDate>)은 RFC 822 형식
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError, OverflowError):
        return raw


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _find_child(item: ET.Element, name: str) -> str:
    for child in item:
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _is_reddit_self_link(link: str) -> bool:
    return "reddit.com" in link and "/comments/" in link


def _entry_link(item: ET.Element) -> str:
    """RSS 2.0 <link>텍스트</link>와 Atom <link href="..."/> 둘 다 처리."""
    fallback = ""
    for child in item:
        name = _local_name(child.tag)
        if name == "link":
            href = (child.attrib.get("href") or "").strip()
            if href:
                if child.attrib.get("rel", "alternate") == "alternate":
                    return href
                fallback = fallback or href
            elif child.text and child.text.strip():
                return child.text.strip()
        elif name == "guid" and child.text and child.text.strip().startswith("http"):
            fallback = fallback or child.text.strip()
    return fallback


def _entry_author(item: ET.Element) -> str:
    """RSS 2.0 <author>텍스트</author>와 Atom <author><name>..</name></author> 둘 다 처리."""
    author = ""
    for child in item:
        if _local_name(child.tag) != "author":
            continue
        for sub in child:
            if _local_name(sub.tag) == "name" and sub.text and sub.text.strip():
                author = sub.text.strip()
                break
        if not author and child.text and child.text.strip():
            author = child.text.strip()
        break
    for prefix in ("/u/", "u/"):
        if author.startswith(prefix):
            return author[len(prefix):]
    return author


_SUBMITTED_TAIL_RE = re.compile(
    r"submitted by\s+/?u/\S+.*$", re.IGNORECASE | re.DOTALL
)


def _entry_selftext(item: ET.Element) -> str:
    """본문 HTML에서 글 내용만 추출. Reddit Atom content에는
    본문(<!-- SC_OFF -->...<!-- SC_ON -->) 뒤에 'submitted by ...' 꼬리가 붙는다."""
    html_body = (
        _find_child(item, "content")
        or _find_child(item, "description")
        or _find_child(item, "summary")
    )
    had_markers = "<!-- SC_OFF -->" in html_body or "<!-- SC_ON -->" in html_body
    if "<!-- SC_OFF -->" in html_body:
        html_body = html_body.split("<!-- SC_OFF -->", 1)[1]
    if "<!-- SC_ON -->" in html_body:
        html_body = html_body.split("<!-- SC_ON -->", 1)[0]

    text = _strip_html(html_body)
    if not had_markers:
        text = _SUBMITTED_TAIL_RE.sub("", text).strip()
    return text


def _entry_post_id(item: ET.Element, link: str) -> str:
    post_id = extract_post_id(link) or ""
    if not post_id:
        raw_id = _find_child(item, "id")
        if raw_id.startswith("t3_"):
            post_id = raw_id[3:]
    return post_id.lower()


def parse_rss_posts(xml_text: str, *, limit: int = 30) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[ET.Element] = []
    for elem in root.iter():
        if _local_name(elem.tag) in ("item", "entry"):
            items.append(elem)

    posts: list[dict[str, Any]] = []
    for item in items:
        title = _find_child(item, "title")
        link = _entry_link(item)
        if not link:
            continue
        link = normalize_reddit_url(link.split("?")[0])
        if not _is_reddit_self_link(link):
            continue

        selftext = _entry_selftext(item)
        author = _entry_author(item)
        created_at = _parse_pubdate(
            _find_child(item, "pubDate")
            or _find_child(item, "published")
            or _find_child(item, "updated")
        )
        post_id = _entry_post_id(item, link)

        posts.append(
            {
                "post_id": post_id,
                "title": title,
                "selftext": selftext,
                "url": link,
                "author": author or "unknown",
                "created_at": created_at,
                "score": 0,
                "num_comments": 0,
                "is_self": True,
                "over_18": False,
                "removed_by_category": None,
                "stickied": False,
                "locked": False,
            }
        )
        if len(posts) >= limit:
            break
    return posts
