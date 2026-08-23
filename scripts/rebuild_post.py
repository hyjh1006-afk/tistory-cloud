# -*- coding: utf-8 -*-
"""이미 올린 글을 새 번역으로 다시 만든다.

번역만 갈아끼우고 번호·사용기록은 건드리지 않는다 (재발행용).
입력 JSON 형식은 scripts/README-rebuild.md 참고.

사용: .venv/bin/python scripts/rebuild_post.py <입력.json>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import github_state  # noqa: E402
from src.config import load_config  # noqa: E402
from src.content_generator import (  # noqa: E402
    BlogItem,
    render_html,
    render_nosleep_html,
)
from src.coupang_links import embed_coupang_links  # noqa: E402
from src.logger_setup import setup_logger  # noqa: E402
from src.manual_translation import post_source_text  # noqa: E402

LOCAL_OUTPUTS = ROOT / "state" / "local_outputs"


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    logger = setup_logger()
    mode = spec["mode"]
    title = spec["title"]
    gemini = load_config().get("gemini")

    if mode == "nosleep":
        post = spec["posts"][0]
        tr = spec["translations"]
        html_content = render_nosleep_html(title, post, tr["translation"], tr.get("summary", ""))
        plain = tr["translation"] + "\n" + tr.get("summary", "")
    else:
        start = int(spec["start_number"])
        items = []
        for index, post in enumerate(spec["posts"]):
            number = start + index
            tr = spec["translations"][str(number)]
            items.append(
                BlogItem(
                    number=number,
                    post=post,
                    source_text=post_source_text(post),
                    translation=tr["translation"].strip(),
                    summary=tr["summary"].strip(),
                )
            )
        html_content = render_html(title, items)
        plain = "\n".join(i.translation + "\n" + i.summary for i in items)

    html_content = embed_coupang_links(html_content, plain, gemini_config=gemini, logger=logger)

    record = {
        "title": title,
        "blog_range": spec["blog_range"],
        "html": html_content,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
    }
    safe = spec["blog_range"].replace("~", "-")
    name = f"{datetime.now():%Y%m%d_%H%M%S}_retrans_{safe}.json"

    LOCAL_OUTPUTS.mkdir(parents=True, exist_ok=True)
    (LOCAL_OUTPUTS / name).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    if not github_state.enabled():
        raise SystemExit("GITHUB_TOKEN/STATE_REPO 가 없습니다 — scripts/rebuild.sh 로 실행하세요.")
    github_state.save_output(name, record)   # 번호·사용기록(push_state)은 일부러 건드리지 않는다
    print(f"GitHub 대기 목록 저장: {name}")
    print(f"제목: {title}")
    print(f"OUTPUT_JSON={LOCAL_OUTPUTS / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
