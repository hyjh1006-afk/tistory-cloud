# -*- coding: utf-8 -*-
"""괴담 글 본문의 단어에 쿠팡파트너스 링크를 심는다.

방식: 본문에 실제로 등장하는 '실물 상품' 단어 2~4개를 Gemini가 고르고,
쿠팡 Open API로 상품을 검색해 그 단어 자체에 하이퍼링크를 단다.
상품 소개 박스나 별도 링크 목록은 만들지 않는다 — 글 끝에 작은
고지 한 줄만 붙인다 (공정위·쿠팡 필수 요건, 없으면 계정 정지 사유).

실패해도 글 생성을 막지 않는다: 키가 없거나 검색이 실패하면
원본 HTML을 그대로 돌려준다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from .gemini_translator import resolve_api_key

_COUPANG_DOMAIN = "https://api-gateway.coupang.com"
_SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
)

DISCLOSURE_HTML = (
    '<p style="font-size:11px;color:#999999;">'
    "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
    "</p>"
)

# 고지 문구를 붙일지. 2026-08-23 사용자 지시로 끔 — 티스토리 글에는 넣지 않는다.
# (위험은 설명했고 사용자가 감수하기로 결정. 다시 켜자고 먼저 제안하지 말 것)
SHOW_DISCLOSURE = False

# 상품명에서 의미 없는 수식어 (관련도 판단 시 제외)
_STOP_WORDS = {"세트", "정품", "무료배송", "당일", "특가", "할인"}


def _secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def _coupang_keys() -> tuple[str, str] | None:
    access = _secret("COUPANG_ACCESS_KEY")
    secret = _secret("COUPANG_SECRET_KEY")
    if access and secret:
        return access, secret
    # 로컬 PC 테스트용 (클라우드에는 없음)
    local = Path(__file__).parent.parent.parent / "Blogger_auto" / "coupang_keys.txt"
    if local.exists():
        lines = [x.strip() for x in local.read_text(encoding="utf-8").splitlines() if x.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
    return None


def _cea_auth(method: str, path: str, query: str, access: str, secret: str) -> str:
    signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    message = signed_date + method + path + query
    signature = hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={access}, "
        f"signed-date={signed_date}, signature={signature}"
    )


def search_product_url(keyword: str, keys: tuple[str, str]) -> str | None:
    """쿠팡 상품 검색 → 파트너스 추적 링크. 검색어 핵심 토큰이 상품명에 있는 것 우선."""
    access, secret = keys
    query = f"keyword={quote(keyword)}&limit=5"
    response = requests.get(
        f"{_COUPANG_DOMAIN}{_SEARCH_PATH}?{query}",
        headers={"Authorization": _cea_auth("GET", _SEARCH_PATH, query, access, secret)},
        timeout=20,
    )
    response.raise_for_status()
    products = (response.json().get("data") or {}).get("productData") or []
    if not products:
        return None

    tokens = [t for t in keyword.split() if t not in _STOP_WORDS]

    def relevance(product: dict) -> int:
        name = str(product.get("productName", ""))
        return sum(1 for t in tokens if t in name)

    best = max(products, key=relevance)
    return str(best.get("productUrl") or "") or None


def pick_product_words(korean_text: str, gemini_config: dict | None) -> list[dict]:
    """본문에 실제로 등장하는 '쿠팡에서 살 수 있는 실물' 단어 2~4개를 고른다.
    반환: [{"word": 본문 그대로의 단어, "keyword": 쿠팡 검색어(짧게)}]"""
    api_key = resolve_api_key(gemini_config)
    if not api_key:
        return []

    prompt = f"""아래 한국어 글에서 '쿠팡에서 파는 실물 상품'에 해당하는 단어를 2~4개 골라라.

규칙:
- word는 반드시 글에 **그 표기 그대로** 등장하는 단어여야 한다 (조사 제외한 명사만. 예: 글에 '손전등을'이 있으면 word는 '손전등').
- 실물이어야 한다: 인형, 거울, 베개, 손전등, 커튼, 시계, 카메라, 담요, 향초 같은 것.
  사람·장소·추상어(엄마, 병원, 공포, 목소리)는 금지.
- keyword는 그 상품을 쿠팡에서 검색할 짧은 검색어 (보통 word와 동일, 필요하면 1단어 보정).
- 마땅한 게 2개가 안 되면 있는 만큼만. 억지로 채우지 마라.

글:
{korean_text[:4000]}

출력은 JSON만: {{"items": [{{"word": "...", "keyword": "..."}}]}}"""

    response = requests.post(
        _GEMINI_URL,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
        },
        timeout=60,
    )
    response.raise_for_status()
    candidates = response.json().get("candidates") or []
    text = "".join(
        p.get("text", "")
        for p in (candidates[0].get("content", {}).get("parts", []) if candidates else [])
    ).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1], strict=False)
    except ValueError:
        return []
    items = []
    for item in data.get("items", []):
        word = str(item.get("word", "")).strip()
        keyword = str(item.get("keyword", "")).strip() or word
        if word:
            items.append({"word": word, "keyword": keyword})
    return items[:4]


def _link_word_in_html(html_content: str, word: str, url: str) -> tuple[str, bool]:
    """HTML 본문 텍스트에서 word의 첫 등장에만 하이퍼링크를 단다.
    제목(h2/h3), 태그 내부(속성 등), 기존 링크 안은 건드리지 않는다."""
    escaped_url = url.replace('"', "%22")
    # (?![^<]*>) : 다음 '<'가 나오기 전에 '>'가 있으면(=태그 안이면) 매칭 금지
    pattern = re.compile(re.escape(word) + r"(?![^<]*>)(?![^<]*</a>)")
    link = f'<a href="{escaped_url}" target="_blank" rel="noopener sponsored">{word}</a>'

    # 제목 블록은 통째로 건너뛰고 본문 조각에서만 치환한다
    segments = re.split(r"(<h[23][^>]*>.*?</h[23]>)", html_content, flags=re.DOTALL)
    for index, segment in enumerate(segments):
        if re.match(r"<h[23]", segment):
            continue
        replaced = pattern.sub(link, segment, count=1)
        if replaced != segment:
            segments[index] = replaced
            return "".join(segments), True
    return html_content, False


# 상품 단어가 부족할 때 쓰는 예비 연결 — 괴담 글에 거의 항상 나오는 단어들.
# (단어, 쿠팡 검색어) 순서대로 시도하며 본문에 있는 단어만 쓴다.
_FALLBACK_PAIRS = [
    ("괴담", "공포 소설"),
    ("공포", "공포 소설"),
    ("이야기", "공포 소설"),
    ("소설", "공포 소설"),
    ("꿈", "공포 소설"),
    ("밤", "무드등"),
    ("새벽", "무드등"),
    ("소리", "무드등"),
    ("집", "도어락"),
    ("문", "도어락"),
]


def embed_coupang_links(
    html_content: str,
    korean_text: str,
    gemini_config: dict | None = None,
    logger: logging.Logger | None = None,
) -> str:
    """본문 단어 2개 이상에 쿠팡 링크를 심고, 성공 시 끝에 고지 한 줄을 붙인다.
    어떤 이유로든 실패하면 원본을 그대로 반환한다 (글 생성을 막지 않음)."""
    try:
        keys = _coupang_keys()
        if not keys:
            if logger:
                logger.info("쿠팡 키 없음 — 링크 생략")
            return html_content

        # 링크는 괴담 본문에만 — 해설 구역(방문자가 잘 안 읽음)은 제외한다
        split = re.search(r"<h2>해설</h2>|<p><strong>\[해설\]</strong></p>", html_content)
        if split:
            body, tail = html_content[: split.start()], html_content[split.start() :]
        else:
            body, tail = html_content, ""

        try:
            words = pick_product_words(korean_text, gemini_config)
        except Exception as exc:
            if logger:
                logger.warning("상품 단어 선정 실패 — 예비 연결로 진행: %s", exc)
            words = []

        linked = 0
        linked_words: set[str] = set()
        result = body
        for item in words:
            if linked >= 3:
                break
            try:
                url = search_product_url(item["keyword"], keys)
            except Exception as exc:
                if logger:
                    logger.warning("쿠팡 검색 실패(%s): %s", item["keyword"], exc)
                continue
            if not url:
                continue
            result, ok = _link_word_in_html(result, item["word"], url)
            if ok:
                linked += 1
                linked_words.add(item["word"])
                if logger:
                    logger.info("쿠팡 링크 삽입: %s", item["word"])

        # 최소 2개 보장: 부족하면 항상 나오는 단어(괴담·공포·밤 등)에 예비 상품 연결
        if linked < 2:
            used_keywords: set[str] = set()
            for pass_allow_reuse in (False, True):
                if linked >= 2:
                    break
                for word, keyword in _FALLBACK_PAIRS:
                    if linked >= 2:
                        break
                    if word in linked_words:
                        continue
                    if not pass_allow_reuse and keyword in used_keywords:
                        continue
                    try:
                        url = search_product_url(keyword, keys)
                    except Exception:
                        continue
                    if not url:
                        continue
                    result, ok = _link_word_in_html(result, word, url)
                    if ok:
                        linked += 1
                        linked_words.add(word)
                        used_keywords.add(keyword)
                        if logger:
                            logger.info("예비 쿠팡 링크 삽입: %s → %s", word, keyword)

        if linked == 0:
            return html_content
        return result + tail + ("\n" + DISCLOSURE_HTML if SHOW_DISCLOSURE else "")
    except Exception as exc:
        if logger:
            logger.warning("쿠팡 링크 처리 실패 — 원본 유지: %s", exc)
        return html_content
