"""🎛️ 파이프라인 HQ — 콘텐츠 자동화 관제탑.

- 📊 대시보드: Blogger·쿠팡·유튜브 지표 + 시간표 원격 조종
- 👻 괴담: 티스토리 글 생성 (수집→Gemini 번역→HTML)
- 🎬 유튜브: 채널 통계 + 영상 즉시 제작
"""

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="파이프라인 HQ", page_icon="🎛️", layout="centered")

# Streamlit secrets → 환경변수 (gemini_translator가 환경변수에서 키를 읽음)
try:
    _gemini_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
except Exception:
    _gemini_key = ""
if _gemini_key:
    os.environ["GEMINI_API_KEY"] = _gemini_key


# ── PIN 잠금 ────────────────────────────────────────────────
# 이 앱에는 '지금 발행/제작/게시' 버튼이 있어 주소만 알면 누구나 실행할 수 있었다.
# 모아이 랩과 같은 PIN을 Streamlit secrets(HQ_PIN)에 넣어 잠근다 (2026-08-02).
def _require_pin() -> None:
    try:
        pin = str(st.secrets.get("HQ_PIN", "")).strip()
    except Exception:
        pin = ""
    if not pin:
        st.error(
            "🔒 PIN이 설정되지 않았습니다.\n\n"
            "Streamlit Cloud → 이 앱 ⋮ → Settings → Secrets 에 아래 한 줄을 추가하세요 "
            "(기존 줄은 지우지 마세요):\n\n"
            '```\nHQ_PIN = "모아이 랩과 같은 PIN"\n```'
        )
        st.stop()
    if st.session_state.get("hq_auth"):
        return
    st.markdown("#### 🔒 파이프라인 HQ")
    entered = st.text_input("PIN", type="password", key="hq_pin_input")
    if st.button("들어가기", type="primary"):
        if entered.strip() == pin:
            st.session_state["hq_auth"] = True
            st.rerun()
        else:
            st.error("PIN이 맞지 않아요")
    st.stop()


_require_pin()

import dashboard
import github_state
from src.json_store import read_json
from src.logger_setup import setup_logger
from src.paths import LAST_NUMBER_PATH, USED_POSTS_PATH
from src.workflow import generate_full_auto

MODE_LABELS = {"two_sentence": "두 줄 괴담 (10개)", "nosleep": "단편 괴담 (1편)"}

st.title("🎛️ 파이프라인 HQ")

# AI 오피스에서 ?view=gwidam&mode=... 으로 열면 괴담 탭이 먼저(활성) 오도록
_qp = st.query_params
_view = _qp.get("view", "")
_qmode = _qp.get("mode", "two_sentence")
if _qmode not in MODE_LABELS:
    _qmode = "two_sentence"

if _view == "gwidam":
    tab_gwidam, tab_dash = st.tabs(["👻 괴담티스토리", "📊 대시보드"])
else:
    tab_dash, tab_gwidam = st.tabs(["📊 대시보드", "👻 괴담티스토리"])


# ══════════════════════════════════════════════════════════
# 공용 헬퍼
# ══════════════════════════════════════════════════════════

def _rich_copy_button(html: str, key: str) -> None:
    """서식(굵기·문단·링크)을 유지한 채 클립보드에 복사하는 버튼."""
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


def _metric_block(loader, cache_key: str):
    """지표를 세션에 캐시해서 표시. 실패하면 안내만."""
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = ("ok", loader())
        except Exception as exc:
            st.session_state[cache_key] = ("err", str(exc))
    return st.session_state[cache_key]


def _run_gwidam(mode: str, start_number: int = 0) -> None:
    """괴담 글 생성 → 대기 목록에 저장. 대시보드/괴담 탭 공용."""
    with st.status("실행 중…", expanded=True) as box:
        st.write("1/3 Reddit 수집 → 2/3 Gemini 번역 → 3/3 HTML 생성")
        logger = setup_logger()
        try:
            result = generate_full_auto(
                logger, mode, start_number_override=int(start_number) or None
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
                safe = result["blog_range"].replace("~", "-")
                github_state.save_output(f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.json", record)
            except Exception as exc:
                st.warning(f"GitHub 저장 실패: {exc}")
            st.session_state.pop("outputs_cache", None)
            box.update(label=f"완료! {result['title']}", state="complete", expanded=False)
            return True
        except Exception as exc:
            logger.exception("gwidam run failed: %s", exc)
            box.update(label="실패", state="error")
            st.error(str(exc))
            return False


def _schedule_editor(label: str, repo: str, key: str) -> None:
    """저장소의 시간표를 조회·수정하는 작은 UI.

    평일/주말이 나뉜 저장소(유튜브)는 칸이 두 개로 나온다.
    """
    try:
        slots, sha = dashboard.get_schedule(repo)
    except Exception as exc:
        st.caption(f"{label} 시간표를 불러오지 못했어요: {exc}")
        return

    inputs = {}
    if len(slots) > 1:
        st.markdown(f"**{label} 시간표** (쉼표로 구분, 한국시간 HH:MM)")
        cols = st.columns(len(slots))
        for col, (name, times) in zip(cols, slots.items()):
            with col:
                inputs[name] = st.text_input(
                    name, value=", ".join(times), key=f"sched_{key}_{name}"
                )
    else:
        name, times = next(iter(slots.items()))
        inputs[name] = st.text_input(
            f"{label} 시간표 (쉼표로 구분, 한국시간 HH:MM)",
            value=", ".join(times),
            key=f"sched_{key}",
        )

    if st.button(f"{label} 시간표 저장", key=f"save_{key}"):
        new_slots = {
            name: [t.strip() for t in raw.split(",") if t.strip()][:6]
            for name, raw in inputs.items()
        }
        try:
            dashboard.save_schedule(repo, new_slots, sha)
            summary = " · ".join(
                f"{n}: {', '.join(v) or '(끔)'}" for n, v in new_slots.items()
            )
            st.success(f"저장 완료 — {summary}")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")


# ══════════════════════════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════════════════════════

with tab_dash:
    st.subheader("🕹️ 원격 조종")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("🎬 유튜브 영상 지금 제작", use_container_width=True):
            try:
                dashboard.trigger_workflow(dashboard.SHORTS_REPO)
                st.success("실행 시작! 5~10분 뒤 유튜브에 업로드됩니다.")
            except Exception as exc:
                st.error(f"실행 실패: {exc}")
    with col_b:
        if st.button("📝 블로거 글 지금 발행", use_container_width=True):
            try:
                dashboard.trigger_workflow(dashboard.BLOGGER_REPO)
                st.success("실행 시작! 2~3분 뒤 블로그에 새 글이 올라옵니다.")
            except Exception as exc:
                st.error(f"실행 실패: {exc}")
    with col_c:
        if st.button("🍚 워드프레스+블루스카이 지금 발행", use_container_width=True):
            try:
                dashboard.trigger_workflow(
                    dashboard.KITCHEN_REPO, dashboard.KITCHEN_WORKFLOW
                )
                st.success("실행 시작! 워드프레스 글 발행 후 블루스카이에 홍보됩니다. (오늘 상한을 채웠으면 건너뜀)")
            except Exception as exc:
                st.error(f"실행 실패: {exc}")

    col_d, col_e = st.columns(2)
    with col_d:
        gen_two = st.button("👻 두 줄 괴담 글 생성", use_container_width=True)
    with col_e:
        gen_nosleep = st.button("👻 단편 괴담 글 생성", use_container_width=True)
    if gen_two or gen_nosleep:
        if _run_gwidam("two_sentence" if gen_two else "nosleep"):
            st.success("생성 완료! '👻 괴담티스토리' 탭에서 복사해 올리세요.")

    _schedule_editor("유튜브 자동 업로드", dashboard.SHORTS_REPO, "shorts")
    _schedule_editor("블로거 자동 발행", dashboard.BLOGGER_REPO, "blogger")
    _schedule_editor("집밥 채널 자동 발행", dashboard.KITCHEN_REPO, "kitchen")

    # ── 지표 ──────────────────────────────────────────────
    st.divider()
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.subheader("📈 지표")
    with top_right:
        if st.button("🔄 새로고침", key="dash_refresh", use_container_width=True):
            for k in ("m_blogger", "m_coupang", "m_youtube", "m_adsense",
                      "m_kitchen", "m_ad_status"):
                st.session_state.pop(k, None)
            st.rerun()

    s_yt, yt = _metric_block(dashboard.youtube_stats, "m_youtube")
    s_bl, bl = _metric_block(dashboard.blogger_stats, "m_blogger")
    s_ki, kitchen = _metric_block(dashboard.kitchen_stats, "m_kitchen")
    s_cp, cp = _metric_block(dashboard.coupang_stats, "m_coupang")
    s_ad, adr = _metric_block(dashboard.adsense_stats, "m_adsense")

    st.markdown("**🎬 유튜브 — 돈의 흐름 읽기**")
    if s_yt == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("구독자", f"{yt['subscribers']:,}")
        c2.metric("총 조회수", f"{yt['views']:,}")
        c3.metric("영상", f"{yt['videos']:,}개")
    else:
        st.caption(f"조회 실패: {yt}")

    st.markdown("**📝 Blogger — AI공부하는 직장인의 개발 노트**")
    if s_bl == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("총 조회수", f"{bl['views_all']:,}")
        c2.metric("최근 7일", f"{bl['views_7d']:,}")
        c3.metric("발행 글", f"{bl['posts']:,}개")
    else:
        st.caption(f"조회 실패: {bl}")

    st.markdown("**🍚 [집밥 워드프레스](https://pparkzzekitchen.wordpress.com/)**")
    if s_ki == "ok":
        wp = kitchen["wordpress"]
        c1, c2, c3 = st.columns(3)
        c1.metric("총 조회수", f"{wp['views_all']:,}")
        c2.metric("최근 7일", f"{wp['views_7d']:,}")
        c3.metric("발행 글", f"{wp['posts']:,}개")

        bsky = kitchen.get("bluesky")
        st.markdown("**🦋 [블루스카이 — @pparkzze.bsky.social](https://bsky.app/profile/pparkzze.bsky.social)**")
        if bsky:
            c1, c2, c3 = st.columns(3)
            c1.metric("팔로워", f"{bsky['followers']:,}")
            c2.metric("게시물", f"{bsky['posts']:,}개")
            c3.metric("반응", f"{bsky['engagements']:,}건")
            st.caption("블루스카이는 게시물 조회수를 공개하지 않아 좋아요·재게시·답글·인용만 실측합니다.")
        else:
            st.caption("블루스카이 계정 연결 전")
        if kitchen.get("updated_at"):
            st.caption(f"마지막 지표 수집: {kitchen['updated_at']}")
    else:
        st.caption(f"조회 실패: {kitchen}")

    st.markdown("**🛒 쿠팡파트너스 (최근 30일)**")
    if s_cp == "ok":
        c1, c2 = st.columns(2)
        c1.metric("클릭", f"{cp['clicks']:,}회")
        c2.metric("수수료", f"{cp['commission']:,.0f}원")
    else:
        st.caption(f"조회 실패: {cp}")

    st.markdown("**💰 애드센스 수익**")
    if s_ad == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("오늘", f"{adr['today']:,.0f}원")
        c2.metric("최근 7일", f"{adr['last_7d']:,.0f}원")
        c3.metric("이번 달", f"{adr['month']:,.0f}원")
    else:
        st.caption(f"미연결: {adr}")

    # 애드센스 승인 현황 (블로거) — 수익 항목에 함께 표시
    s_ads, ad = _metric_block(dashboard.blogger_adsense_status, "m_ad_status")
    if s_ads == "ok":
        state = ad.get("state", "UNKNOWN")
        if ad.get("approved"):
            dday = ad.get("coupang_dday")
            if ad.get("coupang_active_date") and dday is not None and dday > 0:
                coupang = f"쿠팡 링크 D-{dday} ({ad['coupang_active_date']}부터)"
            elif ad.get("coupang_active_date"):
                coupang = "쿠팡 링크 활성 ✅"
            else:
                coupang = "승인 기록 동기화 대기"
            st.caption(f"블로거 애드센스 현황: 승인 완료 ✅ · {coupang}")
        elif state == "GETTING_READY":
            st.caption("블로거 애드센스 현황: 심사 중 🟡 (승인되면 자동 반영)")
        elif state == "REQUIRES_REVIEW":
            st.caption("블로거 애드센스 현황: 심사 대기 🟡 (검토 요청됨)")
        elif state == "NEEDS_ATTENTION":
            st.caption("블로거 애드센스 현황: 확인 필요 🔴")
        else:
            st.caption(f"블로거 애드센스 현황: {state}")
    else:
        st.caption(f"블로거 애드센스 현황: 조회 실패 ({ad})")


# ══════════════════════════════════════════════════════════
# 👻 괴담 (티스토리)
# ══════════════════════════════════════════════════════════

with tab_gwidam:
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

    mode = st.radio(
        "모드",
        options=list(MODE_LABELS),
        format_func=MODE_LABELS.get,
        horizontal=True,
        index=list(MODE_LABELS).index(_qmode),   # AI 오피스 딥링크(?mode=)로 기본값 지정
    )

    start_number = 0
    if mode == "two_sentence":
        start_number = st.number_input(
            "시작 번호 (0 = 자동, 마지막 번호 다음)", min_value=0, step=1, value=0
        )

    if st.button("⚡ 글 생성", type="primary", use_container_width=True):
        _run_gwidam(mode, start_number)

    st.divider()
    outputs = _load_outputs()
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader(f"📬 대기 중인 글 ({len(outputs)})")
    with col_btn:
        if st.button("🔄 새로고침", key="gwidam_refresh", use_container_width=True):
            _invalidate_outputs()
            st.rerun()

    if not outputs:
        st.caption("대기 중인 글이 없어요. 위 버튼으로 만들면 여기 나타납니다.")

    for index, item in enumerate(outputs):
        expanded = index == 0
        with st.expander(
            f"**{item.get('title', '(제목 없음)')}** · {item.get('created_at', '')}",
            expanded=expanded,
        ):
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

    st.caption(
        "생성한 글은 [올렸음]을 누르기 전까지 계속 보관됩니다 — 미리 쌓아뒀다가 날 잡고 예약 발행해도 돼요. "
        "글에 들어간 Reddit 원문은 즉시 기록되어 다시 나오지 않습니다."
    )
