"""괴담 글 생성기 — 폰에서 어디서나 쓰는 클라우드 버전.

- 버튼 한 번: Reddit 수집 → Gemini 번역 → 티스토리용 글 완성
- 매일 자동 생성: schedule.json 시간표대로 GitHub Actions가 만들어 대기 목록에 쌓음
- 만들어진 글은 전부 "대기 중인 글" 목록에 → 복사해서 올리고 [올렸음]으로 제거
"""

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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


def _rich_copy_button(html: str, key: str) -> None:
    """서식(굵기·문단·링크)을 유지한 채 클립보드에 복사하는 버튼.
    티스토리 모바일 앱의 일반 에디터에 그대로 붙여넣으면 된다."""
    payload = json.dumps(html)
    components.html(
        f"""
        <div id="src-{key}" contenteditable="true"
             style="position:absolute; left:-99999px; top:0;"></div>
        <button id="cp-{key}"
          style="width:100%; padding:14px; font-size:16px; font-weight:bold;
                 background:#ff4b4b; color:white; border:none; border-radius:8px;
                 cursor:pointer;">
          📋 본문 복사 (서식 유지)
        </button>
        <script>
        (() => {{
          const html = {payload};
          const btn = document.getElementById("cp-{key}");
          btn.addEventListener("click", () => {{
            const src = document.getElementById("src-{key}");
            src.innerHTML = html;
            const range = document.createRange();
            range.selectNodeContents(src);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            let ok = false;
            try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
            sel.removeAllRanges();
            src.innerHTML = "";
            btn.innerText = ok ? "✅ 복사 완료! 티스토리 본문에 붙여넣으세요"
                               : "❌ 복사 실패 — 원본 HTML을 길게 눌러 복사하세요";
            setTimeout(() => {{ btn.innerText = "📋 본문 복사 (서식 유지)"; }}, 4000);
          }});
        }})();
        </script>
        """,
        height=60,
    )


def _load_outputs() -> list[dict]:
    if "outputs_cache" not in st.session_state:
        try:
            st.session_state["outputs_cache"] = github_state.list_outputs()
        except Exception as exc:
            st.warning(f"대기 목록을 못 불러왔어요: {exc}")
            st.session_state["outputs_cache"] = []
    return st.session_state["outputs_cache"]


def _invalidate_outputs() -> None:
    st.session_state.pop("outputs_cache", None)


# ── 글 생성 ──────────────────────────────────────────────
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
            record = {
                "title": result["title"],
                "blog_range": result["blog_range"],
                "html": html,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "mode": mode,
            }
            try:
                github_state.push_state()
                safe_range = result["blog_range"].replace("~", "-")
                name = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_range}.json"
                github_state.save_output(name, record)
            except Exception as exc:
                st.warning(f"GitHub 저장 실패 (글은 아래 목록 대신 여기 한정 표시): {exc}")
                st.session_state["outputs_cache"] = _load_outputs() + [record]
            else:
                _invalidate_outputs()
            status.update(label="완료! 아래 대기 목록에서 복사하세요", state="complete", expanded=False)
        except Exception as exc:
            logger.exception("cloud run failed: %s", exc)
            status.update(label="실패", state="error")
            st.error(str(exc))

# ── 대기 중인 글 목록 ─────────────────────────────────────
st.divider()
outputs = _load_outputs()
col_title, col_btn = st.columns([3, 1])
with col_title:
    st.subheader(f"📬 대기 중인 글 ({len(outputs)})")
with col_btn:
    if st.button("🔄 새로고침", use_container_width=True):
        _invalidate_outputs()
        st.rerun()

if not outputs:
    st.caption("대기 중인 글이 없어요. 자동 생성 시간이 되거나 위 버튼으로 만들면 여기 쌓입니다.")

for index, item in enumerate(outputs):
    expanded = index == 0
    with st.expander(f"**{item.get('title', '(제목 없음)')}** · {item.get('created_at', '')}", expanded=expanded):
        tab_copy, tab_preview, tab_html = st.tabs(["📋 복사", "👀 미리보기", "</> 원본 HTML"])

        with tab_copy:
            st.markdown("**① 제목** — 복사해서 티스토리 제목칸에")
            st.code(item.get("title", ""), language=None)
            st.markdown("**② 본문** — 버튼 누르고 티스토리 본문에 붙여넣기")
            _rich_copy_button(item.get("html", ""), key=f"out{index}")

        with tab_preview:
            st.html(item.get("html", ""))

        with tab_html:
            st.caption("PC에서 HTML 모드로 붙일 때만 사용")
            st.code(item.get("html", ""), language="html")

        if item.get("_name") and st.button(
            "✅ 올렸음 (목록에서 제거)", key=f"done{index}", use_container_width=True
        ):
            try:
                github_state.delete_output(item["_name"], item["_sha"])
                _invalidate_outputs()
                st.rerun()
            except Exception as exc:
                st.error(f"제거 실패: {exc}")

st.divider()
st.caption(
    "자동 생성 시간표는 GitHub의 schedule.json에서 바꿀 수 있어요 (한국시간, 30분 단위). "
    "글에 들어간 Reddit 원문은 즉시 기록되어 다시 나오지 않습니다."
)
