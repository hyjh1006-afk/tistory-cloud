# -*- coding: utf-8 -*-
"""쿠팡 파트너스 대가성 고지 — 글 맨 위 상자 한 줄 (의존성 없음: 발행 스크립트들이 그대로 import 한다).

2026-11-22 대표님 결정으로 다시 켬(8/23 「안 넣음」을 바꿈): 「글 맨 위에 눈에 덜 띄게 한 줄」.
근거는 공정위 「추천·보증 등에 관한 표시·광고 심사지침」(예규 제499호, 2026.6.1) Ⅴ.6 —
블로그 글은 표시문구를 「제목 또는 첫 부분」에, 본문과 구분되게(글자색·크기·상자), 「수수료를 받는다」가 분명한 말로.
맨 밑 회색 작은 글씨는 지침이 직접 든 부적절 예(작은 글씨·배경과 비슷한 색)라 쓰지 않는다.
"""
from __future__ import annotations

import re

DISCLOSURE_TEXT = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
# 티스토리 편집기 기본 「인용 상자」(style3) — 붙여넣기에서도 살아남고 본문과 구분된다
DISCLOSURE_HTML = f'<blockquote data-ke-style="style3">{DISCLOSURE_TEXT}</blockquote>'
_MARK = "쿠팡 파트너스 활동"


def has_coupang(html: str) -> bool:
    return "link.coupang.com" in (html or "") or "coupang.com/vp/" in (html or "")


def ensure_disclosure(html: str) -> str:
    """쿠팡 링크가 있는데 고지가 없으면 맨 앞에 넣는다. 예전 맨 밑 회색 고지가 있으면 지우고 맨 위로 올린다."""
    if not has_coupang(html):
        return html
    html = re.sub(r'\s*<p[^>]*>\s*' + re.escape(DISCLOSURE_TEXT) + r'\s*</p>', "", html)
    if _MARK in re.sub(r"<[^>]+>", "", html):
        return html
    return DISCLOSURE_HTML + "\n" + html
