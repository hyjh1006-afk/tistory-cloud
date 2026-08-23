# -*- coding: utf-8 -*-
"""괴담 글 생성 (CLI). 단계를 나눠서 부를 수 있다.

  prompt <mode>  : Reddit 수집 → 번역 프롬프트만 만든다 (output/chatgpt_prompt.txt)
                   → 번역은 클로드가 직접 하고 output/translation_result.txt 에 쓴다
  finish         : translation_result.txt 를 읽어 HTML 완성 + 상태 저장
  auto <mode>    : 옛 방식 — 번역까지 제미나이 API로 한 번에 (예비용)

mode 는 two_sentence | nosleep.
결과 경로는 마지막 줄 `OUTPUT_JSON=` 으로 출력한다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import github_state  # noqa: E402
from src.logger_setup import setup_logger  # noqa: E402
from src.paths import CHATGPT_PROMPT_PATH, TRANSLATION_RESULT_PATH  # noqa: E402
from src.workflow import (  # noqa: E402
    build_final_from_translation_result,
    generate_full_auto,
    generate_nosleep_prompt,
    generate_translation_prompt,
)

LOCAL_OUTPUTS = ROOT / "state" / "local_outputs"
MODES = {"two_sentence", "nosleep"}


def _save_and_push(result: dict, mode: str) -> Path:
    html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    record = {
        "title": result["title"],
        "blog_range": result["blog_range"],
        "html": html,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
    }
    safe = result["blog_range"].replace("~", "-")
    name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.json"

    LOCAL_OUTPUTS.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_OUTPUTS / name
    local_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    # 클라우드 앱과 상태를 맞춘다 (번호·사용기록 + 대기 목록)
    try:
        print(github_state.push_state(), flush=True)
        github_state.save_output(name, record)
        print(f"GitHub 대기 목록 저장: {name}", flush=True)
    except Exception as exc:  # 저장 실패해도 글은 살린다
        print(f"GitHub 저장 실패(로컬 파일은 있음): {exc}", file=sys.stderr, flush=True)

    print(f"제목: {record['title']}")
    print(f"OUTPUT_JSON={local_path}")
    return local_path


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("사용법: run_gwidam.py prompt|finish|auto [two_sentence|nosleep]", file=sys.stderr)
        return 2

    stage = args[0]
    if stage in MODES:  # 옛 호출 방식 (모드만 넘기면 제미나이 자동)
        stage, mode = "auto", stage
    else:
        mode = args[1] if len(args) > 1 else "two_sentence"

    if stage in {"prompt", "auto"} and mode not in MODES:
        print(f"알 수 없는 모드: {mode}", file=sys.stderr)
        return 2

    logger = setup_logger()

    if stage == "prompt":
        print(github_state.pull_state(), flush=True)
        if mode == "nosleep":
            result = generate_nosleep_prompt(logger)
        else:
            result = generate_translation_prompt(logger)
        TRANSLATION_RESULT_PATH.write_text("", encoding="utf-8")  # 지난 번역 잔재 제거
        print(f"제목(임시): {result['title']}")
        print(f"PROMPT_FILE={CHATGPT_PROMPT_PATH}")
        print(f"RESULT_FILE={TRANSLATION_RESULT_PATH}")
        return 0

    if stage == "finish":
        raw = TRANSLATION_RESULT_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            print("translation_result.txt 가 비어 있습니다. 번역을 먼저 쓰세요.", file=sys.stderr)
            return 1
        result = build_final_from_translation_result(logger)
        pending_mode = json.loads(
            (ROOT / "output" / "pending_posts.json").read_text(encoding="utf-8")
        ).get("mode", "two_sentence")
        _save_and_push(result, pending_mode)
        return 0

    if stage == "auto":
        print(github_state.pull_state(), flush=True)
        result = generate_full_auto(logger, mode)
        _save_and_push(result, mode)
        return 0

    print(f"알 수 없는 단계: {stage}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
