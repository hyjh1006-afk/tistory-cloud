# -*- coding: utf-8 -*-
"""GitHub Actions에서 실행되는 자동 글 생성.

state/ 폴더의 기록을 루트로 복사 → 글 생성 → 결과를 state/outputs/에,
갱신된 기록을 state/에 다시 복사. 커밋/푸시는 워크플로우가 담당한다.

사용: python daily_generate.py [two_sentence|nosleep]
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
STATE_NAMES = ["last_number.json", "used_posts.json", "reddit_daily.json"]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "two_sentence"
    if mode not in ("two_sentence", "nosleep"):
        print(f"알 수 없는 모드: {mode}")
        return 1

    # state/ → 루트 (엔진은 루트의 기록 파일을 읽는다)
    for name in STATE_NAMES:
        src = BASE / "state" / name
        if src.exists():
            shutil.copy(src, BASE / name)

    from src.logger_setup import setup_logger
    from src.workflow import generate_full_auto

    logger = setup_logger()
    try:
        result = generate_full_auto(logger, mode)
    except Exception as exc:
        message = str(exc)
        print(f"생성 실패: {message}")
        # 쿨다운/일시적 제한은 실패로 치지 않는다 (다음 슬롯에 다시 시도됨)
        if "간격" in message or "다시 시도" in message:
            return 0
        return 1

    html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    record = {
        "title": result["title"],
        "blog_range": result["blog_range"],
        "html": html,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
    }

    outputs_dir = BASE / "state" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    safe_range = result["blog_range"].replace("~", "-")
    out_path = outputs_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_range}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    # 루트 → state/ (갱신된 번호/사용 기록 반영)
    for name in STATE_NAMES:
        src = BASE / name
        if src.exists():
            shutil.copy(src, BASE / "state" / name)

    print(f"생성 완료: {result['title']} → {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
