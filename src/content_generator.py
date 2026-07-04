import html
import re
from dataclasses import dataclass
from typing import Any

from .manual_translation import post_source_text


@dataclass
class BlogItem:
    number: int
    post: dict[str, Any]
    source_text: str
    translation: str
    summary: str


KEYWORD_THEMES = [
    (("mother", "father", "mom", "dad", "parent", "parents"), "가족이라는 가장 익숙한 관계가 불안의 근원으로 바뀌는 이야기"),
    (("child", "kid", "baby", "daughter", "son"), "아이의 순진한 말이나 행동 뒤에 섬뜩한 진실이 숨어 있는 이야기"),
    (("house", "room", "door", "window", "bed"), "평범한 생활 공간이 갑자기 안전하지 않은 장소로 변하는 이야기"),
    (("dead", "corpse", "grave", "funeral", "ghost"), "죽음이 끝이 아니라는 불길한 가능성을 건드리는 이야기"),
    (("phone", "text", "call", "message"), "연락 수단을 통해 알 수 없는 존재나 과거의 흔적이 드러나는 이야기"),
    (("mirror", "reflection", "shadow"), "눈앞의 모습과 현실이 어긋나며 정체성의 공포를 만드는 이야기"),
    (("sleep", "dream", "nightmare", "wake"), "잠과 꿈의 경계가 무너지며 현실감이 흔들리는 이야기"),
    (("doctor", "hospital", "patient", "surgery"), "치료와 구조의 공간이 오히려 위협으로 뒤집히는 이야기"),
    (("smile", "laugh", "voice", "whisper"), "사소한 소리나 표정이 설명할 수 없는 위화감을 남기는 이야기"),
]


def clean_source_text(post: dict[str, Any]) -> str:
    text = f"{post.get('title', '')} {post.get('selftext', '')}"
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def infer_theme(source_text: str) -> str:
    lowered = source_text.lower()
    for keywords, theme in KEYWORD_THEMES:
        if any(keyword in lowered for keyword in keywords):
            return theme
    return "일상적인 상황이 마지막 순간에 전혀 다른 의미로 뒤집히는 이야기"


def make_korean_summary(post: dict[str, Any]) -> str:
    theme = infer_theme(clean_source_text(post))
    return f"{theme}입니다."


def build_blog_items(
    posts: list[dict[str, Any]],
    start_number: int,
    translations: dict[int, dict[str, str]],
) -> list[BlogItem]:
    items: list[BlogItem] = []
    for index, post in enumerate(posts):
        number = start_number + index
        translated = translations.get(number, {})
        items.append(
            BlogItem(
                number=number,
                post=post,
                source_text=post_source_text(post),
                translation=translated.get("translation", "").strip(),
                summary=translated.get("summary", "").strip() or make_korean_summary(post),
            )
        )
    return items


def make_blog_title(start_number: int, end_number: int) -> str:
    return f"[Reddit] 두 줄 괴담 모음 {start_number}~{end_number}"


def render_markdown(title: str, items: list[BlogItem]) -> str:
    lines: list[str] = [title, ""]

    for item in items:
        post = item.post
        lines.extend(
            [
                f"{item.number}.",
                "",
                item.source_text,
                item.translation,
                "",
                "원문 링크:",
                post["url"],
                f"작성자: u/{post['author']}",
                "",
                "",
            ]
        )

    lines.extend(["", "", "", "해설", ""])
    for item in items:
        lines.append(f"{item.number}: {item.summary}")

    return "\n".join(lines).rstrip() + "\n"


def paragraph(text: str) -> str:
    escaped = html.escape(text).replace("\n", "<br>")
    return f"<p>{escaped}</p>"


def render_html(title: str, items: list[BlogItem]) -> str:
    blocks: list[str] = [f"<h2>{html.escape(title)}</h2>", "<br>"]

    for item in items:
        post = item.post
        url = html.escape(post["url"], quote=True)
        author = html.escape(post["author"])

        blocks.extend(
            [
                f"<h3>{item.number}.</h3>",
                paragraph(item.source_text),
                paragraph(item.translation),
                "<br>",
                paragraph("원문 링크:"),
                (
                    "<p>"
                    f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
                    "</p>"
                ),
                paragraph(f"작성자: u/{author}"),
                "<br>",
                "<br>",
            ]
        )

    blocks.extend(["<br>", "<br>", "<br>", "<h2>해설</h2>"])
    for item in items:
        blocks.append(paragraph(f"{item.number}: {item.summary}"))

    return "\n".join(blocks)


def make_nosleep_title(post: dict[str, Any]) -> str:
    return f"[Reddit] {post['title']}"


def strip_repeated_title(translation: str, title: str) -> str:
    text = translation.strip()
    title_text = title.replace("[Reddit]", "", 1).strip()
    if not title_text:
        return text

    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and lines[0].strip().rstrip(".。!?") == title_text.rstrip(".。!?"):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
        return "\n".join(lines).strip()

    return text


def render_nosleep_markdown(
    title: str,
    post: dict[str, Any],
    translation: str,
    summary: str,
) -> str:
    body_translation = strip_repeated_title(translation, title)
    lines = [
        title,
        "",
        body_translation,
        "",
        "",
        "",
        "[해설]",
        summary.strip(),
        "",
        "원문 링크:",
        post["url"],
        f"작성자: u/{post['author']}",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_nosleep_html(
    title: str,
    post: dict[str, Any],
    translation: str,
    summary: str,
) -> str:
    url = html.escape(post["url"], quote=True)
    author = html.escape(post["author"])
    body_translation = strip_repeated_title(translation, title)
    blocks = [
        f"<h2>{html.escape(title)}</h2>",
        "<br>",
        paragraph(body_translation),
        "<br>",
        "<br>",
        "<br>",
        "<p><strong>[해설]</strong></p>",
        paragraph(summary.strip()),
        "<br>",
        paragraph("원문 링크:"),
        (
            "<p>"
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
            "</p>"
        ),
        paragraph(f"작성자: u/{author}"),
    ]
    return "\n".join(blocks)
