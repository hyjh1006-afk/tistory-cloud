import html
import logging
import re
from typing import Any, Callable

import requests

from .json_store import read_json, write_json
from .paths import LAST_NUMBER_PATH

StartNumberProvider = Callable[[int], int]


TITLE_RANGE_PATTERN = re.compile(
    r"\[Reddit\]\s*두\s*줄\s*괴담\s*모음\s*(\d+)\s*[~-]\s*(\d+)",
    re.IGNORECASE,
)


def get_local_last_number() -> int:
    data = read_json(LAST_NUMBER_PATH, {"last_number": 0})
    return int(data.get("last_number", 0))


def extract_last_number_from_text(text: str) -> int | None:
    matches = TITLE_RANGE_PATTERN.findall(html.unescape(text))
    if not matches:
        return None
    return max(int(end) for _start, end in matches)


def fetch_category_last_number(category_url: str) -> int | None:
    if not category_url:
        return None

    response = requests.get(
        category_url,
        headers={"User-Agent": "tistory-reddit-horror-bot/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    return extract_last_number_from_text(response.text)


def get_next_range(
    count: int = 10,
    config: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
    start_number_provider: StartNumberProvider | None = None,
    start_number_override: int | None = None,
) -> tuple[int, int]:
    if start_number_override is not None:
        if start_number_override < 1:
            raise ValueError("시작 번호는 1 이상이어야 합니다.")
        return start_number_override, start_number_override + count - 1

    last_number = get_local_last_number()
    numbering_config = (config or {}).get("numbering", {})
    tistory_config = (config or {}).get("tistory", {})

    if numbering_config.get("source") == "category_page":
        detected_number = False
        try:
            remote_last_number = fetch_category_last_number(
                tistory_config.get("category_url", "")
            )
            if remote_last_number is not None:
                detected_number = True
                last_number = max(last_number, remote_last_number)
                if logger:
                    logger.info("Category page last number: %s", remote_last_number)
            elif logger:
                logger.warning("No matching Reddit range title found on category page.")
        except Exception as exc:
            if logger:
                logger.warning("Failed to read category last number: %s", exc)
            if not numbering_config.get("fallback_to_local", True):
                raise

        if not detected_number and start_number_provider:
            manual_start = int(start_number_provider(last_number + 1))
            if manual_start < 1:
                raise ValueError("시작 번호는 1 이상이어야 합니다.")
            return manual_start, manual_start + count - 1

    start = last_number + 1
    end = last_number + count
    return start, end


def update_last_number(last_number: int) -> None:
    write_json(LAST_NUMBER_PATH, {"last_number": last_number})
