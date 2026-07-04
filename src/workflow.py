import logging
from typing import Any, Callable

from .config import load_config
from .gemini_translator import translate_prompt
from .content_generator import (
    build_blog_items,
    make_blog_title,
    make_nosleep_title,
    render_html,
    render_markdown,
    render_nosleep_html,
    render_nosleep_markdown,
)
from .duplicates import UsedPostStore
from .json_store import read_json, write_json
from .manual_translation import build_chatgpt_prompt, build_nosleep_prompt, parse_translation_result
from .numbering import get_next_range, update_last_number
from .output_writer import save_output_files
from .paths import CHATGPT_PROMPT_PATH, PENDING_POSTS_PATH, TRANSLATION_RESULT_PATH
from .reddit_client import RedditClient, select_unused_posts
from .reddit_errors import REDDIT_COLLECT_FAILED_MSG, RedditCollectError


def generate_translation_prompt(
    logger: logging.Logger,
    start_number_provider: Callable[[int], int] | None = None,
    start_number_override: int | None = None,
) -> dict[str, Any]:
    config = load_config()
    start_number, end_number = get_next_range(
        10,
        config=config,
        logger=logger,
        start_number_provider=start_number_provider,
        start_number_override=start_number_override,
    )
    blog_range = f"{start_number}~{end_number}"
    title = make_blog_title(start_number, end_number)

    logger.info("Start blog range: %s", blog_range)
    reddit = RedditClient(config["reddit"])
    used_store = UsedPostStore()

    try:
        posts = reddit.fetch_posts(logger=logger)
    except RedditCollectError as exc:
        raise RuntimeError(str(exc) or REDDIT_COLLECT_FAILED_MSG) from exc
    logger.info("Fetched %s reddit posts", len(posts))

    selected_posts = select_unused_posts(posts, used_store, count=10)
    logger.info("Selected %s unused eligible posts", len(selected_posts))

    if len(selected_posts) < 10:
        raise RuntimeError(
            f"사용 가능한 글이 10개보다 적습니다. 현재 선별 개수: {len(selected_posts)}"
        )

    # 프롬프트에 들어간 글은 이 시점에 바로 사용됨으로 기록한다.
    # 최종 생성까지 기다리면 그 사이에 뽑은 프롬프트끼리 같은 글이 중복된다.
    used_store.add_posts(selected_posts, blog_range)
    logger.info("Marked %s posts as used (range %s)", len(selected_posts), blog_range)

    CHATGPT_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_chatgpt_prompt(title, start_number, selected_posts)
    CHATGPT_PROMPT_PATH.write_text(prompt, encoding="utf-8")

    if not TRANSLATION_RESULT_PATH.exists():
        TRANSLATION_RESULT_PATH.write_text("", encoding="utf-8")

    pending = {
        "mode": "two_sentence",
        "title": title,
        "blog_range": blog_range,
        "start_number": start_number,
        "end_number": end_number,
        "selected_posts": selected_posts,
    }
    write_json(PENDING_POSTS_PATH, pending)

    logger.info("Saved ChatGPT prompt: %s", CHATGPT_PROMPT_PATH)
    logger.info("Saved pending posts: %s", PENDING_POSTS_PATH)

    return {
        "mode": "two_sentence",
        "title": title,
        "blog_range": blog_range,
        "prompt_path": str(CHATGPT_PROMPT_PATH),
        "prompt_text": prompt,
        "translation_result_path": str(TRANSLATION_RESULT_PATH),
        "selected_posts": selected_posts,
    }


def generate_nosleep_prompt(logger: logging.Logger) -> dict[str, Any]:
    config = load_config()
    reddit_config = dict(config["reddit"])
    reddit_config.update(
        {
            "subreddit": "nosleep",
            "sort": "hot",
            "fetch_limit": 1,
        }
    )

    reddit = RedditClient(reddit_config)
    used_store = UsedPostStore()

    try:
        posts = reddit.fetch_posts(logger=logger)
    except RedditCollectError as exc:
        raise RuntimeError(str(exc) or REDDIT_COLLECT_FAILED_MSG) from exc
    logger.info("Fetched %s nosleep posts", len(posts))

    selected_posts = select_unused_posts(posts, used_store, count=1)
    if len(selected_posts) < 1:
        raise RuntimeError("사용 가능한 r/nosleep 글을 찾지 못했습니다.")

    post = selected_posts[0]
    title = make_nosleep_title(post)
    blog_range = f"nosleep_{post['post_id']}"
    # 프롬프트 생성 시점에 바로 사용됨으로 기록 (중복 선정 방지)
    used_store.add_posts(selected_posts, blog_range)
    prompt = build_nosleep_prompt(post)

    CHATGPT_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHATGPT_PROMPT_PATH.write_text(prompt, encoding="utf-8")

    if not TRANSLATION_RESULT_PATH.exists():
        TRANSLATION_RESULT_PATH.write_text("", encoding="utf-8")

    pending = {
        "mode": "nosleep",
        "title": title,
        "blog_range": blog_range,
        "selected_posts": selected_posts,
    }
    write_json(PENDING_POSTS_PATH, pending)

    logger.info("Saved nosleep ChatGPT prompt: %s", CHATGPT_PROMPT_PATH)
    logger.info("Saved pending nosleep post: %s", PENDING_POSTS_PATH)

    return {
        "mode": "nosleep",
        "title": title,
        "blog_range": blog_range,
        "prompt_path": str(CHATGPT_PROMPT_PATH),
        "prompt_text": prompt,
        "translation_result_path": str(TRANSLATION_RESULT_PATH),
        "selected_posts": selected_posts,
    }


def generate_full_auto(
    logger: logging.Logger,
    mode: str = "two_sentence",
    start_number_override: int | None = None,
) -> dict[str, Any]:
    """수집 → Gemini 번역 → 최종 HTML/MD까지 한 번에.
    ChatGPT 수동 복붙 단계를 Gemini API 호출로 대체한다."""
    if mode == "nosleep":
        prompt_result = generate_nosleep_prompt(logger)
    else:
        prompt_result = generate_translation_prompt(
            logger,
            start_number_override=start_number_override,
        )

    config = load_config()
    logger.info("Gemini 번역 요청 중…")
    answer = translate_prompt(
        prompt_result["prompt_text"],
        gemini_config=config.get("gemini"),
        logger=logger,
    )

    TRANSLATION_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_RESULT_PATH.write_text(answer.strip(), encoding="utf-8")

    result = build_final_from_translation_result(logger)
    result["prompt_text"] = prompt_result["prompt_text"]
    return result


def build_final_from_translation_result(logger: logging.Logger) -> dict[str, Any]:
    pending = read_json(PENDING_POSTS_PATH, {})
    if not pending:
        raise RuntimeError("pending_posts.json이 없습니다. 먼저 번역 프롬프트를 생성해 주세요.")

    mode = pending.get("mode", "two_sentence")
    title = pending["title"]
    blog_range = pending["blog_range"]
    selected_posts = pending["selected_posts"]

    result_text = TRANSLATION_RESULT_PATH.read_text(encoding="utf-8")
    translations = parse_translation_result(result_text, pending)

    if mode == "nosleep":
        post = selected_posts[0]
        translated = translations.get(1)
        if not translated:
            raise RuntimeError("translation_result.txt에 number 1 번역 결과가 없습니다.")

        final_title = (
            f"[Reddit] {translated['title_translation']}"
            if translated.get("title_translation")
            else title
        )
        html_content = render_nosleep_html(
            final_title,
            post,
            translated["translation"],
            translated.get("summary", ""),
        )
        markdown_content = render_nosleep_markdown(
            final_title,
            post,
            translated["translation"],
            translated.get("summary", ""),
        )

        output_paths = save_output_files(
            html_content=html_content,
            markdown_content=markdown_content,
            blog_range=blog_range,
        )
        logger.info("Saved HTML file: %s", output_paths["html"])
        logger.info("Saved Markdown file: %s", output_paths["markdown"])

        used_store = UsedPostStore()
        used_store.add_posts(selected_posts, blog_range)

        return {
            "title": final_title,
            "blog_range": blog_range,
            "output_paths": output_paths,
            "selected_posts": selected_posts,
        }

    start_number = int(pending["start_number"])
    end_number = int(pending["end_number"])
    missing_numbers = [
        start_number + index
        for index in range(len(selected_posts))
        if start_number + index not in translations
    ]
    if missing_numbers:
        raise RuntimeError(
            "translation_result.txt에 누락된 번호가 있습니다: "
            + ", ".join(str(number) for number in missing_numbers)
        )

    items = build_blog_items(selected_posts, start_number, translations)
    html_content = render_html(title, items)
    markdown_content = render_markdown(title, items)

    output_paths = save_output_files(
        html_content=html_content,
        markdown_content=markdown_content,
        blog_range=blog_range,
    )
    logger.info("Saved HTML file: %s", output_paths["html"])
    logger.info("Saved Markdown file: %s", output_paths["markdown"])

    used_store = UsedPostStore()
    used_store.add_posts(selected_posts, blog_range)
    update_last_number(end_number)
    logger.info("Updated last_number to %s", end_number)

    return {
        "title": title,
        "blog_range": blog_range,
        "output_paths": output_paths,
        "selected_posts": selected_posts,
    }
