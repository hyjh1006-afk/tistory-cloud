import re
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .json_store import read_json, write_json
from .paths import USED_POSTS_PATH


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "share_id",
    "rdt",
}

POST_ID_PATTERN = re.compile(r"/comments/([a-z0-9]+)/", re.IGNORECASE)


def extract_post_id(url: str) -> str | None:
    match = POST_ID_PATTERN.search(url or "")
    if match:
        return match.group(1).lower()
    return None


def normalize_reddit_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower().replace("old.reddit.com", "www.reddit.com")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") + "/"

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(filtered_query)

    return urlunparse((scheme, netloc, path, "", query, ""))


class UsedPostStore:
    def __init__(self) -> None:
        self.data: dict[str, Any] = read_json(USED_POSTS_PATH, {"used_posts": []})
        self.data.setdefault("used_posts", [])
        self.used_ids = {
            item.get("post_id")
            for item in self.data["used_posts"]
            if item.get("post_id")
        }
        self.used_urls = {
            normalize_reddit_url(item.get("url", ""))
            for item in self.data["used_posts"]
            if item.get("url")
        }

    def is_used(self, post_id: str | None, url: str) -> bool:
        normalized_url = normalize_reddit_url(url)

        if post_id and post_id in self.used_ids:
            return True
        return normalized_url in self.used_urls

    def add_posts(self, posts: list[dict[str, Any]], blog_range: str) -> None:
        today = date.today().isoformat()
        changed = False
        for post in posts:
            url = normalize_reddit_url(post["url"])
            post_id = post.get("post_id") or extract_post_id(url)
            # 이미 기록된 글은 중복 저장하지 않는다 (프롬프트 단계와 최종 단계 양쪽에서 호출됨)
            if (post_id and post_id in self.used_ids) or url in self.used_urls:
                continue
            self.data["used_posts"].append(
                {
                    "post_id": post_id,
                    "url": url,
                    "title": post["title"],
                    "blog_range": blog_range,
                    "used_at": today,
                }
            )
            if post_id:
                self.used_ids.add(post_id)
            self.used_urls.add(url)
            changed = True

        if changed:
            write_json(USED_POSTS_PATH, self.data)
