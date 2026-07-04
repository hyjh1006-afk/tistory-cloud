REDDIT_COLLECT_FAILED_MSG = "Reddit 정책/차단으로 자동수집 실패"


class RedditCollectError(RuntimeError):
    """Reddit 자동 수집 실패 (번역/글 생성 단계로 진행하지 않음)."""
