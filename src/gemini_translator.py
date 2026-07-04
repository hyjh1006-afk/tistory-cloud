"""Gemini API 번역 — ChatGPT 수동 복붙을 대체하는 자동 번역.

무료 티어 REST 직접 호출 (별도 패키지 불필요).
키 우선순위: config.json gemini.api_key > 환경변수 GEMINI_API_KEY > 레지스트리(HKCU\\Environment).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

DEFAULT_MODEL = "gemini-2.5-flash"
API_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

NO_KEY_MSG = (
    "Gemini API 키를 찾지 못했습니다.\n"
    "환경변수 GEMINI_API_KEY를 설정하거나 config.json의 gemini.api_key에 넣어주세요."
)


class GeminiError(RuntimeError):
    pass


def _key_from_registry() -> str:
    """환경변수 등록 직후 재로그인 없이도 읽히도록 레지스트리 폴백.
    윈도우 전용 — 리눅스(클라우드)에서는 조용히 빈 값."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
            return str(value).strip()
    except (ImportError, OSError):
        return ""


def resolve_api_key(gemini_config: dict[str, Any] | None = None) -> str:
    config_key = str((gemini_config or {}).get("api_key", "")).strip()
    return (
        config_key
        or os.environ.get("GEMINI_API_KEY", "").strip()
        or _key_from_registry()
    )


def translate_prompt(
    prompt: str,
    *,
    gemini_config: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
    timeout: int = 180,
) -> str:
    """프롬프트를 Gemini에 보내고 답변 텍스트를 돌려준다."""
    api_key = resolve_api_key(gemini_config)
    if not api_key:
        raise GeminiError(NO_KEY_MSG)

    model = str((gemini_config or {}).get("model", "")).strip() or DEFAULT_MODEL
    url = API_URL_TMPL.format(model=model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            # 두줄괴담 10개 JSON 답변이 잘리지 않도록 넉넉하게
            "maxOutputTokens": 8192,
        },
    }

    last_error = ""
    for attempt in range(3):
        if attempt > 0:
            wait = 20 * attempt
            if logger:
                logger.warning("Gemini 재시도 %s/2 — %s초 대기 (%s)", attempt, wait, last_error)
            time.sleep(wait)
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                json=body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.status_code == 429:
            last_error = "429 rate limit"
            continue
        if response.status_code >= 500:
            last_error = f"서버 오류 {response.status_code}"
            continue
        if response.status_code != 200:
            raise GeminiError(
                f"Gemini API 오류 {response.status_code}: {response.text[:300]}"
            )

        text = _extract_text(response.json())
        if text.strip():
            if logger:
                logger.info("Gemini 번역 성공 (%s, %s자)", model, len(text))
            return text
        last_error = "빈 응답"

    raise GeminiError(f"Gemini 번역 실패: {last_error}")


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "\n".join(str(p.get("text", "")) for p in parts if p.get("text"))
