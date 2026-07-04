from typing import Any

from .reddit_collect import collect_reddit_posts
from .reddit_errors import RedditCollectError

__all__ = [
    "RedditClient",
    "RedditCollectError",
    "is_eligible_post",
    "select_unused_posts",
]


class RedditClient:
    """백그라운드 RSS → headless Playwright 수집 래퍼."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def fetch_posts(self, *, logger: Any = None) -> list[dict[str, Any]]:
        subreddit = self.config.get("subreddit", "TwoSentenceHorror")
        sort = self.config.get("sort", "new")
        collect_cfg = self.config.get("collect") or {}
        daily_max = int(collect_cfg.get("daily_max_posts", 10))
        fetch_limit = min(int(self.config.get("fetch_limit", daily_max)), daily_max)

        return collect_reddit_posts(
            self.config,
            subreddit=subreddit,
            sort=sort,
            max_posts=fetch_limit,
            logger=logger,
        )


def is_eligible_post(post: dict[str, Any]) -> tuple[bool, str]:
    title = post.get("title", "").strip()
    selftext = post.get("selftext", "").strip()
    combined = f"{title} {selftext}".strip()
    word_count = len(combined.split())

    if not post.get("post_id"):
        return False, "missing post id"
    if post.get("stickied"):
        return False, "stickied"
    if not post.get("is_self"):
        return False, "link post"
    if post.get("over_18"):
        return False, "nsfw"
    if post.get("removed_by_category"):
        return False, "removed"
    if title.lower() in {"[deleted]", "[removed]"}:
        return False, "deleted title"
    if selftext.lower() in {"[deleted]", "[removed]"}:
        return False, "deleted body"
    if word_count < 12:
        return False, "too short"
    return True, "ok"


def select_unused_posts(
    posts: list[dict[str, Any]], used_store: Any, count: int = 10
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for post in posts:
        eligible, _reason = is_eligible_post(post)
        if not eligible:
            continue

        if used_store.is_used(post.get("post_id"), post["url"]):
            continue

        selected.append(post)
        if len(selected) == count:
            break

    return selected
