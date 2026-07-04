import json
import re
from typing import Any


def post_source_text(post: dict[str, Any]) -> str:
    parts = []
    title = str(post.get("title", "")).strip()
    body = str(post.get("selftext", "")).strip()

    if title:
        parts.append(title)
    if body:
        parts.extend(line.strip() for line in body.splitlines() if line.strip())

    return "\n".join(parts).strip()


def build_chatgpt_prompt(
    title: str,
    start_number: int,
    posts: list[dict[str, Any]],
) -> str:
    lines = [
        "아래 Reddit 두 줄 괴담 10개를 한국어로 자연스럽게 번역해줘.",
        "",
        "중요 조건:",
        "- 원문 제목과 본문을 모두 빠짐없이 번역할 것",
        "- 제목도 한국어로 자연스럽게 번역해 title_translation에 넣을 것",
        "- translation에는 본문 번역만 넣고 제목 번역을 반복하지 말 것",
        "- 원문 의미를 왜곡하지 말 것",
        "- 직역투를 피하되, 괴담 특유의 불길하고 섬뜩한 분위기를 살릴 것",
        "- 한국어 독자가 읽었을 때 짧은 공포 이야기처럼 자연스럽게 느껴지게 할 것",
        "- 원문에 없는 해설이나 설정을 번역문에 덧붙이지 말 것",
        "- 각 글마다 짧은 요약도 1문장으로 작성할 것",
        "- JSON 형식으로 출력해도 되고, 번호별 번역문·요약만 순서대로 적어도 됨",
        "",
        "출력 형식 (JSON 예시):",
        "[",
        '  {"number": 191, "translation": "한국어 번역문", "summary": "짧은 요약"},',
        '  {"number": 192, "translation": "한국어 번역문", "summary": "짧은 요약"}',
        "]",
        "",
        f"글 제목: {title}",
        "",
        "번역할 원문:",
        "",
    ]

    for index, post in enumerate(posts):
        number = start_number + index
        lines.extend(
            [
                f"{number}.",
                f"작성자: u/{post['author']}",
                f"원문 링크: {post['url']}",
                "원문:",
                post_source_text(post),
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def build_nosleep_prompt(post: dict[str, Any]) -> str:
    lines = [
        "아래 Reddit r/nosleep 단편 괴담 1개를 한국어로 자연스럽게 번역해줘.",
        "",
        "중요 조건:",
        "- 원문 제목과 본문을 모두 빠짐없이 번역할 것",
        "- 원문 의미를 왜곡하지 말 것",
        "- 직역투를 피하되, 단편 괴담 특유의 불길하고 서늘한 분위기를 살릴 것",
        "- 한국어 독자가 읽었을 때 공포 단편처럼 자연스럽게 느껴지게 할 것",
        "- 내용상 장면이나 호흡이 구분되는 곳에는 빈 줄을 두 번 넣어 문단을 나눌 것",
        "- 원문에 없는 해설이나 설정을 번역문에 덧붙이지 말 것",
        "- 국문 요약은 글이 긴 점을 고려해 2~3줄 정도로 작성할 것",
        "- JSON 형식으로 출력해도 되고, 번역문 전체와 [해설]만 적어도 됨",
        "",
        "출력 형식 (JSON 예시) — 반드시 이 키 순서대로 (summary를 translation보다 먼저):",
        "[",
        '  {"number": 1, "title_translation": "한국어 제목", "summary": "2~3줄 국문 요약", "translation": "한국어 번역문"}',
        "]",
        "",
        f"원문 제목: {post['title']}",
        f"작성자: u/{post['author']}",
        f"원문 링크: {post['url']}",
        "",
        "원문:",
        post_source_text(post),
    ]

    return "\n".join(lines).rstrip() + "\n"


def _empty_item() -> dict[str, str]:
    return {
        "title_translation": "",
        "translation": "",
        "summary": "",
        "source": "",
        "url": "",
        "author": "unknown",
    }


def _item_from_dict(item: dict[str, Any]) -> dict[str, str]:
    return {
        "title_translation": _normalize_text_field(
            str(item.get("title_translation", ""))
        ),
        "translation": _normalize_text_field(str(item.get("translation", ""))),
        "summary": _normalize_text_field(str(item.get("summary", ""))),
        "source": _normalize_text_field(
            str(item.get("source", item.get("source_text", "")))
        ),
        "url": str(item.get("url", "")).strip(),
        "author": str(item.get("author", "")).strip() or "unknown",
    }


def _normalize_text_field(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    if "\\n" in value and "\n" not in value:
        value = (
            value.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
        )
    return value


def _looks_like_json_payload(raw: str) -> bool:
    text = raw.strip()
    if not text:
        return False
    if text.startswith("```") or text.startswith("[") or text.startswith("{"):
        return True
    markers = (
        '"title_translation"',
        '"translation"',
        '"summary"',
        '"number"',
    )
    return any(marker in text for marker in markers)


def _extract_json_string_value(raw: str, field: str) -> str:
    marker = f'"{field}"'
    idx = raw.find(marker)
    if idx < 0:
        return ""

    colon = raw.find(":", idx + len(marker))
    if colon < 0:
        return ""

    quote_start = raw.find('"', colon + 1)
    if quote_start < 0:
        return ""

    chars: list[str] = []
    i = quote_start + 1
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            chars.append(raw[i : i + 2])
            i += 2
            continue
        if ch == '"':
            j = i + 1
            while j < len(raw) and raw[j] in " \t\r\n":
                j += 1
            if j < len(raw) and raw[j] in ",}]":
                break
        chars.append(ch)
        i += 1

    return _normalize_text_field("".join(chars))


def _parse_loose_json_translations(raw: str) -> dict[int, dict[str, str]] | None:
    body = _strip_code_fence(raw.strip())
    if not _looks_like_json_payload(body):
        return None

    translations: dict[int, dict[str, str]] = {}
    matches = list(re.finditer(r'"number"\s*:\s*(\d+)', body))
    if matches:
        for idx, match in enumerate(matches):
            number = int(match.group(1))
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
            chunk = body[start:end]
            item = _empty_item()
            item.update(
                {
                    "title_translation": _extract_json_string_value(
                        chunk, "title_translation"
                    ),
                    "translation": _extract_json_string_value(chunk, "translation"),
                    "summary": _extract_json_string_value(chunk, "summary"),
                    "source": _extract_json_string_value(chunk, "source"),
                    "url": _extract_json_string_value(chunk, "url"),
                    "author": _extract_json_string_value(chunk, "author") or "unknown",
                }
            )
            if item["translation"]:
                translations[number] = item
        if translations:
            return translations

    number_text = _extract_json_string_value(body, "number")
    number = int(number_text) if number_text.isdigit() else 1
    item = _empty_item()
    item.update(
        {
            "title_translation": _extract_json_string_value(body, "title_translation"),
            "translation": _extract_json_string_value(body, "translation"),
            "summary": _extract_json_string_value(body, "summary"),
            "source": _extract_json_string_value(body, "source"),
            "url": _extract_json_string_value(body, "url"),
            "author": _extract_json_string_value(body, "author") or "unknown",
        }
    )
    if not item["translation"]:
        return None
    return {number: item}


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    blocks = re.findall(
        r"```(?:json)?[^\n`]*\r?\n([\s\S]*?)```",
        stripped,
        flags=re.IGNORECASE,
    )
    if blocks:
        for block in blocks:
            if "[" in block:
                return block.strip()
        return blocks[-1].strip()

    open_fence = re.search(
        r"```(?:json)?[^\n`]*\r?\n([\s\S]+)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if open_fence:
        return open_fence.group(1).strip()

    legacy_fence = re.search(
        r"```(?:json)?\s*([\s\S]*?)```",
        stripped,
        flags=re.IGNORECASE,
    )
    if legacy_fence:
        body = legacy_fence.group(1).strip()
        if body.startswith("id=") or body.startswith('id="'):
            newline = body.find("\n")
            if newline >= 0:
                body = body[newline + 1 :].strip()
        return body

    return stripped


def _extract_json_candidate(raw: str) -> str:
    text = _strip_code_fence(raw.strip())

    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        text = text[start : end + 1]

    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r",\s*]", "]", text)
    text = re.sub(r",\s*}", "}", text)
    return text


def _parse_json_translations(raw: str) -> dict[int, dict[str, str]] | None:
    candidate = _extract_json_candidate(raw)
    if not candidate:
        return None

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None

    translations: dict[int, dict[str, str]] = {}
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        number = int(item.get("number", index))
        parsed = _item_from_dict(item)
        if not parsed["translation"]:
            continue
        translations[number] = parsed

    return translations or None


def _extract_translation_summary(block: str) -> tuple[str, str]:
    text = block.strip()
    if not text:
        return "", ""

    for pattern in (
        r"(?m)^\[해설\]\s*",
        r"(?m)^해설:\s*",
        r"(?m)^요약:\s*",
        r"(?m)^summary:\s*",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            summary = text[match.end() :].strip()
            translation = text[: match.start()].strip()
            return translation, summary

    return text, ""


def _split_numbered_blocks(text: str) -> list[str]:
    parts = re.split(r"(?m)^(?:###\s*)?(\d{1,3})\.\s*", text.strip())
    if len(parts) > 2:
        blocks = [part.strip() for part in parts[2::2] if part.strip()]
        if blocks:
            return blocks
    return []


def _split_story_blocks(text: str) -> list[str]:
    numbered = _split_numbered_blocks(text)
    if numbered:
        return numbered

    dashed = [part.strip() for part in re.split(r"\n-{3,}\n", text) if part.strip()]
    if len(dashed) > 1:
        return dashed

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text.strip()) if part.strip()]
    return paragraphs


def _parse_nosleep_plain(raw: str) -> dict[int, dict[str, str]]:
    loose = _parse_loose_json_translations(raw)
    if loose:
        return loose

    body = raw.strip()
    title_translation = ""
    summary = ""

    for marker in ("[해설]", "해설:", "요약:", "Summary:"):
        if marker in body:
            head, tail = body.split(marker, 1)
            body = head.strip()
            summary = tail.strip()
            break

    lines = body.splitlines()
    if lines and len(lines[0].strip()) <= 80 and not lines[0].strip().endswith((".", "!", "?", "…")):
        title_translation = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

    translation, inline_summary = _extract_translation_summary(body)
    if inline_summary and not summary:
        summary = inline_summary
        body = translation

    if not body:
        raise ValueError("번역 본문을 찾지 못했습니다.")

    item = _empty_item()
    item.update(
        {
            "title_translation": title_translation,
            "translation": body,
            "summary": summary,
        }
    )
    return {1: item}


def _parse_two_sentence_plain(raw: str, pending: dict[str, Any]) -> dict[int, dict[str, str]]:
    start_number = int(pending["start_number"])
    expected_count = len(pending.get("selected_posts", []))
    if expected_count <= 0:
        raise ValueError("pending_posts.json에 선택된 글이 없습니다.")

    blocks = _split_story_blocks(raw)
    if len(blocks) < expected_count:
        raise ValueError(
            f"번역 {expected_count}개가 필요한데 {len(blocks)}개만 인식했습니다. "
            "빈 줄, ---, 또는 번호(231.)로 구분해 주세요."
        )

    translations: dict[int, dict[str, str]] = {}
    for index in range(expected_count):
        number = start_number + index
        block = blocks[index]
        translation, summary = _extract_translation_summary(block)
        if not translation:
            raise ValueError(f"{number}번 번역문을 찾지 못했습니다.")
        item = _empty_item()
        item.update({"translation": translation, "summary": summary})
        translations[number] = item

    return translations


def _parse_plain_with_pending(raw: str, pending: dict[str, Any]) -> dict[int, dict[str, str]]:
    mode = pending.get("mode", "two_sentence")
    if mode == "nosleep":
        return _parse_nosleep_plain(raw)
    return _parse_two_sentence_plain(raw, pending)


def normalize_two_sentence_numbers(
    translations: dict[int, dict[str, str]],
    pending: dict[str, Any],
) -> dict[int, dict[str, str]]:
    if pending.get("mode", "two_sentence") != "two_sentence":
        return translations

    start_number = int(pending["start_number"])
    expected_count = len(pending.get("selected_posts", []))
    if expected_count <= 0 or not translations:
        return translations

    expected_keys = set(range(start_number, start_number + expected_count))
    if set(translations.keys()) == expected_keys:
        return translations

    ordered_numbers = sorted(translations.keys())
    if len(ordered_numbers) != expected_count:
        return translations

    return {
        start_number + index: translations[number]
        for index, number in enumerate(ordered_numbers)
    }


def parse_translation_result(
    text: str,
    pending: dict[str, Any],
) -> dict[int, dict[str, str]]:
    raw = text.strip()
    if not raw:
        raise ValueError("번역 답변이 비어 있습니다.")

    json_result = _parse_json_translations(raw)
    if not json_result:
        json_result = _parse_loose_json_translations(raw)

    if json_result:
        mode = pending.get("mode", "two_sentence")
        expected_count = len(pending.get("selected_posts", []))
        if mode == "two_sentence" and expected_count > 0:
            if len(json_result) != expected_count:
                json_result = None
            else:
                return normalize_two_sentence_numbers(json_result, pending)

    if json_result:
        return json_result

    parsed = _parse_plain_with_pending(raw, pending)
    if pending.get("mode", "two_sentence") == "two_sentence":
        return normalize_two_sentence_numbers(parsed, pending)
    return parsed
