"""Reddit 백그라운드 수집 (클라우드판): 직접 RSS → 프록시 폴백."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Any

from .json_store import read_json, write_json
from .paths import REDDIT_DAILY_PATH
from .reddit_errors import REDDIT_COLLECT_FAILED_MSG, RedditCollectError
from .reddit_proxy import fetch_via_proxies
from .reddit_rss import fetch_via_rss, is_blocked_response, parse_rss_posts


def default_rss_urls(subreddit: str, sort: str = "new") -> list[str]:
    # limit=100: 한 요청으로 최대한 깊게 받아 사용된 글을 걸러도 10개가 남게 한다
    urls = [
        f"https://old.reddit.com/r/{subreddit}/new/.rss?limit=100",
        f"https://www.reddit.com/r/{subreddit}/new/.rss?limit=100",
        f"https://old.reddit.com/r/{subreddit}/top/.rss?t=day&limit=100",
    ]
    if sort == "hot":
        urls.insert(
            0,
            f"https://old.reddit.com/r/{subreddit}/hot/.rss?limit=100",
        )
    return urls


DEFAULT_USER_AGENT = (
    "windows:tistory-reddit-generator:1.2 (by /u/tistory_reddit_desktop)"
)


def _sanitize_user_agent(value: Any) -> str:
    """HTTP 헤더는 latin-1만 허용된다. 한글 등 비ASCII가 섞이면
    요청 자체가 실패하므로 제거하고, 남는 게 없으면 기본값을 쓴다."""
    user_agent = str(value or "").strip()
    user_agent = user_agent.encode("ascii", "ignore").decode("ascii").strip()
    return user_agent or DEFAULT_USER_AGENT


RATE_LIMIT_MSG = (
    "Reddit이 이 IP의 요청을 일시적으로 제한하고 있습니다 (429/403).\n"
    "짧은 시간에 여러 번 실행하면 제한이 길어집니다. 1~2시간 후 다시 시도하세요."
)


def _block_status(exc: Exception) -> int | None:
    """403/429 응답이면 상태 코드를 돌려주고, 아니면 None."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if status in (403, 429) else None


def _retry_after_seconds(exc: Exception) -> int | None:
    """429 응답이면 대기할 초를 돌려주고, 아니면 None."""
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) != 429:
        return None
    try:
        retry_after = int(response.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        retry_after = 0
    # Reddit 비로그인 RSS는 분 단위로 제한하는 것으로 관측됨 — 최소 60초 대기
    return min(max(retry_after, 60), 180)


def _collect_config(reddit_config: dict[str, Any]) -> dict[str, Any]:
    return reddit_config.get("collect") or {}


def _delay(reddit_config: dict[str, Any]) -> None:
    cfg = _collect_config(reddit_config)
    lo = float(cfg.get("delay_min_sec", 3))
    hi = float(cfg.get("delay_max_sec", 7))
    time.sleep(random.uniform(lo, hi))


def _rss_url_list(
    reddit_config: dict[str, Any], subreddit: str, sort: str
) -> list[str]:
    cfg = _collect_config(reddit_config)
    custom = cfg.get("rss_urls")
    if custom:
        return [str(u) for u in custom]
    return default_rss_urls(subreddit, sort)


def _assert_cooldown_passed(subreddit: str, reddit_config: dict[str, Any]) -> None:
    """직전 수집 후 일정 시간(기본 10분)이 지나야 재수집 허용.
    짧은 간격 연타는 Reddit rate limit(429/403)을 부르는 것이 관측됨."""
    cfg = _collect_config(reddit_config)
    if cfg.get("skip_daily_limit"):
        return
    cooldown_min = float(cfg.get("cooldown_minutes", 10))
    data = read_json(REDDIT_DAILY_PATH, {"runs": {}})
    last_run = data.get("runs", {}).get(subreddit, "")
    if not last_run:
        return
    try:
        last_dt = datetime.fromisoformat(last_run)
    except ValueError:
        return  # 옛 형식이면 통과
    remaining = cooldown_min * 60 - (datetime.now() - last_dt).total_seconds()
    if remaining > 0:
        minutes = int(remaining // 60) + 1
        raise RedditCollectError(
            f"Reddit 요청 제한을 피하려면 수집 간격이 필요합니다.\n"
            f"약 {minutes}분 후에 다시 시도하세요. "
            f"(급하면 프롬프트 직접 입력으로 진행 가능)"
        )


def _mark_collect_success(subreddit: str) -> None:
    data = read_json(REDDIT_DAILY_PATH, {"runs": {}})
    data.setdefault("runs", {})[subreddit] = datetime.now().isoformat(timespec="seconds")
    write_json(REDDIT_DAILY_PATH, data)


def collect_reddit_posts(
    reddit_config: dict[str, Any],
    *,
    subreddit: str,
    sort: str = "new",
    max_posts: int = 10,
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]]:
    """
    읽기 전용 수집. 제목·본문·URL·작성시간만.
    RSS 실패 시 headless Playwright. 둘 다 실패 시 RedditCollectError.
    """
    _assert_cooldown_passed(subreddit, reddit_config)
    cfg = _collect_config(reddit_config)
    daily_cap = int(cfg.get("daily_max_posts", 10))
    fetch_cap = min(max_posts, daily_cap)
    # 후보 풀은 넉넉하게 — 이미 사용한 글을 걸러낸 뒤에도 fetch_cap개가 남아야 한다
    pool_cap = max(fetch_cap * 3, 150)

    urls = _rss_url_list(reddit_config, subreddit, sort)
    user_agent = _sanitize_user_agent(reddit_config.get("user_agent"))

    if logger:
        logger.info("Reddit RSS 수집 시도 (%s개 URL)", len(urls))

    posts: list[dict[str, Any]] = []
    rss_errors: list[str] = []
    blocked_count = 0

    for idx, url in enumerate(urls):
        if idx > 0:
            _delay(reddit_config)
        for attempt in range(2):
            try:
                xml_text = fetch_via_rss(url, user_agent=user_agent)
                batch = parse_rss_posts(xml_text, limit=pool_cap)
                if batch:
                    posts = batch
                    if logger:
                        logger.info("RSS 수집 성공: %s (%s건)", url, len(posts))
                    break
                if is_blocked_response(xml_text, status_code=200):
                    rss_errors.append(f"RSS blocked: {url}")
                    break
            except Exception as exc:
                # 클라우드에서는 긴 대기 없이 바로 다음 경로/프록시로 넘어간다
                if _block_status(exc) is not None:
                    blocked_count += 1
                rss_errors.append(f"{url}: {exc}")
                if logger:
                    logger.warning("RSS 실패 %s: %s", url, exc)
            break
        if posts:
            break
        # 두 URL 연속 429/403이면 이 서버 IP가 차단된 것 — 직접 요청은 그만하고 프록시로
        if blocked_count >= 2:
            if logger:
                logger.warning("Reddit이 서버 IP를 차단 중 — 프록시 경유로 전환")
            break

    if not posts:
        if logger:
            logger.info("직접 RSS 실패 — 프록시 경유 시도")
        try:
            posts = fetch_via_proxies(urls, limit=pool_cap, logger=logger)
        except Exception as exc:
            if logger:
                logger.exception("프록시 수집 실패: %s", exc)
            raise RedditCollectError(REDDIT_COLLECT_FAILED_MSG) from exc

    if not posts:
        if logger:
            logger.error("Reddit 수집 실패. RSS: %s", "; ".join(rss_errors))
        raise RedditCollectError(REDDIT_COLLECT_FAILED_MSG)

    _mark_collect_success(subreddit)
    return posts[:pool_cap]
