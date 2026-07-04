"""괴담 글 생성기 — 폰에서 어디서나 쓰는 클라우드 버전.

Reddit 수집 → Gemini 번역 → 티스토리용 HTML까지 버튼 한 번.
번호/사용 기록은 GitHub 저장소(state/)에 보존된다.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="괴담 글 생성기", page_icon="👻", layout="centered")

# Streamlit secrets → 환경변수 (gemini_translator가 환경변수에서 키를 읽음)
# secrets 파일이 아예 없으면(로컬 테스트) 접근만으로 예외가 나므로 감싼다
try:
    _gemini_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
except Exception:
    _gemini_key = ""
if _gemini_key:
    os.environ["GEMINI_API_KEY"] = _gemini_key

import github_state
from src.json_store import read_json
from src.logger_setup import setup_logger
from src.paths import LAST_NUMBER_PATH, USED_POSTS_PATH
from src.workflow import generate_full_auto

MODE_LABELS = {"two_sentence": "두 줄 괴담 (10개)", "nosleep": "단편 괴담 (1편)"}

st.title("👻 괴담 글 생성기")

# 세션당 1회: GitHub에서 번호/사용 기록 내려받기
if "state_pulled" not in st.session_state:
    try:
        st.session_state["state_pulled"] = github_state.pull_state()
    except Exception as exc:
        st.session_state["state_pulled"] = f"상태 동기화 실패: {exc}"

last_number = read_json(LAST_NUMBER_PATH, {"last_number": 0}).get("last_number", 0)
used_count = len(read_json(USED_POSTS_PATH, {"used_posts": []}).get("used_posts", []))
st.caption(
    f"마지막 번호: **{last_number}** · 사용한 글: **{used_count}건** · "
    f"{st.session_state['state_pulled']}"
)

mode = st.radio(
    "모드",
    options=list(MODE_LABELS),
    format_func=MODE_LABELS.get,
    horizontal=True,
)

start_number = 0
if mode == "two_sentence":
    start_number = st.number_input(
        "시작 번호 (0 = 자동, 마지막 번호 다음)", min_value=0, step=1, value=0
    )

if st.button("⚡ 글 생성", type="primary", use_container_width=True):
    st.session_state.pop("result", None)
    with st.status("실행 중…", expanded=True) as status:
        st.write("1/3 Reddit 수집 → 2/3 Gemini 번역 → 3/3 HTML 생성")
        logger = setup_logger()
        try:
            result = generate_full_auto(
                logger,
                mode,
                start_number_override=int(start_number) or None,
            )
            html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
            # 폰이 결과 화면을 놓쳐도 다시 열면 복구되도록 결과도 함께 저장
            github_state.LAST_OUTPUT_PATH.write_text(
                json.dumps(
                    {
                        "title": result["title"],
                        "blog_range": result["blog_range"],
                        "html": html,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            try:
                sync_msg = github_state.push_state()
            except Exception as exc:
                sync_msg = f"⚠️ GitHub 저장 실패 (글은 정상 생성): {exc}"
            st.session_state["result"] = {
                "title": result["title"],
                "blog_range": result["blog_range"],
                "html": html,
                "sync": sync_msg,
            }
            status.update(label="완료!", state="complete", expanded=False)
        except Exception as exc:
            logger.exception("cloud run failed: %s", exc)
            status.update(label="실패", state="error")
            st.error(str(exc))
    if "result" in st.session_state:
        st.rerun()

def _show_output(title: str, html: str, blog_range: str, sync_msg: str = "") -> None:
    st.success(f"**{title}** 생성 완료")
    if sync_msg:
        st.caption(sync_msg)

    st.subheader("티스토리에 붙여넣을 HTML")
    st.caption("오른쪽 위 복사 아이콘 → 티스토리 앱 글쓰기(HTML 모드)에 붙여넣기")
    st.code(html, language="html")

    with st.expander("미리보기"):
        st.html(html)

    st.download_button(
        "HTML 파일 다운로드",
        data=html,
        file_name=f"reddit_horror_{blog_range.replace('~', '-')}.html",
        mime="text/html",
        use_container_width=True,
    )


if "result" in st.session_state:
    r = st.session_state["result"]
    _show_output(r["title"], r["html"], r["blog_range"], r["sync"])
elif github_state.LAST_OUTPUT_PATH.exists():
    # 이번 세션에 만든 글은 없지만, 이전에 만든 글이 저장돼 있으면 복구해서 보여준다
    # (버튼 누르고 다른 앱 갔다 와도 여기서 다시 볼 수 있음)
    try:
        last = json.loads(github_state.LAST_OUTPUT_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        last = None
    if last and last.get("html"):
        st.info(f"📄 최근 생성한 글 ({last.get('created_at', '')})")
        _show_output(last["title"], last["html"], last.get("blog_range", ""))

st.divider()
st.caption(
    "글 생성 버튼을 누르면 사용된 Reddit 글이 즉시 기록되어 다시 나오지 않습니다. "
    "수집은 10분 간격 제한이 있습니다."
)
