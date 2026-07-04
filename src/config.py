from copy import deepcopy
from typing import Any

from .json_store import read_json, write_json
from .paths import CONFIG_PATH


DEFAULT_CONFIG: dict[str, Any] = {
    "reddit": {
        "subreddit": "TwoSentenceHorror",
        "sort": "top",
        "time_filter": "week",
        "fetch_limit": 100,
        "user_agent": "windows:tistory-reddit-generator:1.2 (by /u/tistory_reddit_desktop)",
    },
    "tistory": {
        "blog_name": "tester188",
        "category_path": "레딧 짧은 괴담 번역/두 줄 괴담",
        "category_url": "https://tester188.tistory.com/category/%EB%A0%88%EB%94%A7%20%EC%A7%A7%EC%9D%80%20%EA%B4%B4%EB%8B%B4%20%EB%B2%88%EC%97%AD/%EB%91%90%20%EC%A4%84%20%EA%B4%B4%EB%8B%B4",
    },
    "numbering": {
        "source": "category_page",
        "fallback_to_local": True,
    },
    "gemini": {
        "api_key": "",
        "model": "gemini-2.5-flash",
    },
    "output": {},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    config = read_json(CONFIG_PATH, DEFAULT_CONFIG)
    merged = deep_merge(DEFAULT_CONFIG, config)

    if config != merged:
        write_json(CONFIG_PATH, merged)

    return merged
