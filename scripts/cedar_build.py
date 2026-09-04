# -*- coding: utf-8 -*-
"""시더빌 종합병원 리마스터 번역본 → 티스토리 붙여넣기용 HTML.

4년 전 원본 글과 같은 포맷을 그대로 따른다:
  (빈 줄) → <h2>제목</h2> → 원출처 링크 → "원작자에게 허락받은 번역본입니다." → 본문

입력 파일 형식 (UTF-8 텍스트):
  1줄: 제목
  2줄: 원문 링크
  3줄: (빈 줄)
  4줄~: 본문. 빈 줄로 문단을 나눈다.

사용: scripts/cedar.sh build <입력.txt>
결과: state/local_outputs/ 에 저장하고 GitHub 대기 목록에도 올린다(브라우저가 fetch 해 간다).
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import github_state  # noqa: E402

LOCAL_OUTPUTS = ROOT / "state" / "local_outputs"
NOTE = "원작자에게 허락받은 번역본입니다."


def render(title: str, source_url: str, paragraphs: list[str]) -> str:
    body = "<br><br>".join(html.escape(p).replace("\n", "<br>") for p in paragraphs)
    url = html.escape(source_url, quote=True)
    return (
        '<p data-ke-size="size16">&nbsp;</p>'
        f'<h2 data-ke-size="size26">{html.escape(title)}</h2>'
        '<p data-ke-size="size16">'
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
        "<span><i>원출처</i></span></a><br><br>"
        f"{NOTE}<br><br><br><br>"
        f"{body}"
        "</p>"
    )


def main() -> int:
    src = Path(sys.argv[1])
    lines = src.read_text(encoding="utf-8").split("\n")
    title, source_url = lines[0].strip(), lines[1].strip()
    rest = "\n".join(lines[2:]).strip()
    paragraphs = [p.strip() for p in rest.split("\n\n") if p.strip()]
    if not title or not source_url or not paragraphs:
        print("제목·원문링크·본문이 다 있어야 합니다.", file=sys.stderr)
        return 2

    html_content = render(title, source_url, paragraphs)
    record = {
        "title": title,
        "blog_range": src.stem,
        "html": html_content,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "cedar_remaster",
    }
    name = f"cedar_{src.stem}.json"

    LOCAL_OUTPUTS.mkdir(parents=True, exist_ok=True)
    (LOCAL_OUTPUTS / name).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    if not github_state.enabled():
        raise SystemExit("GITHUB_TOKEN/STATE_REPO 가 없습니다 — scripts/cedar.sh 로 실행하세요.")
    # 같은 이름이 이미 있으면 지우고 새로 올린다 (덮어쓰기가 안 되는 API라서)
    for o in github_state.list_outputs():
        if o["_name"] == name:
            github_state.delete_output(name, o["_sha"])
    github_state.save_output(name, record)

    print(f"제목: {title}")
    print(f"문단 {len(paragraphs)}개 · 본문 {len(html_content)}자")
    print(f"RAW=https://raw.githubusercontent.com/hyjh1006-afk/tistory-cloud/main/state/outputs/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
