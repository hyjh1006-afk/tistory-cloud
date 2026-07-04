from datetime import datetime

from .paths import OUTPUT_DIR


def save_output_files(
    html_content: str,
    markdown_content: str,
    blog_range: str,
) -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_range = blog_range.replace("~", "-")
    base_name = f"reddit_horror_{safe_range}_{timestamp}"

    html_path = OUTPUT_DIR / f"{base_name}.html"
    markdown_path = OUTPUT_DIR / f"{base_name}.md"

    # Tistory editor paste target: keep this as a body-only HTML fragment.
    html_path.write_text(html_content, encoding="utf-8")
    markdown_path.write_text(markdown_content, encoding="utf-8")

    return {
        "html": str(html_path),
        "markdown": str(markdown_path),
    }
