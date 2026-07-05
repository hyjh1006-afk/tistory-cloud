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

import dashboard
import github_state
from src.json_store import read_json
from src.logger_setup import setup_logger
from src.paths import LAST_NUMBER_PATH, USED_POSTS_PATH
from src.workflow import generate_full_auto

MODE_LABELS = {"two_sentence": "두 줄 괴담 (10개)", "nosleep": "단편 괴담 (1편)"}

st.title("🎛️ 파이프라인 HQ")

# 탭을 라디오로 구현 — 대시보드 버튼에서 프로그램적으로 탭 전환하기 위함
TABS = ["📊 대시보드", "👻 괴담티스토리", "🎬 경제유튜브"]
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = TABS[0]
active_tab = st.radio(
    "메뉴", TABS, horizontal=True, label_visibility="collapsed", key="active_tab"
)


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


def _schedule_editor(label: str, repo: str, key: str) -> None:
    """저장소의 schedule.json times를 조회·수정하는 작은 UI."""
    try:
        times, sha = dashboard.get_schedule(repo)
    except Exception as exc:
        st.caption(f"{label} 시간표를 불러오지 못했어요: {exc}")
        return
    raw = st.text_input(
        f"{label} 시간표 (쉼표로 구분, 한국시간 30분 단위)",
        value=", ".join(times),
        key=f"sched_{key}",
    )
    if st.button(f"{label} 시간표 저장", key=f"save_{key}"):
        new_times = [t.strip() for t in raw.split(",") if t.strip()][:6]
        try:
            dashboard.save_schedule(repo, new_times, sha)
            st.success(f"저장 완료: {', '.join(new_times) or '(자동 생성 끔)'}")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")


# ══════════════════════════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════════════════════════

def _go_gwidam(mode: str) -> None:
    """대시보드에서 괴담 탭으로 전환 + 자동 생성 예약.
    on_click 콜백에서 호출 — 위젯 생성 전에 실행되므로 active_tab 수정 가능."""
    st.session_state["active_tab"] = TABS[1]
    st.session_state["gwidam_autorun"] = mode


if active_tab == TABS[0]:
    st.subheader("🕹️ 원격 조종")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📝 블로거 글 지금 발행", use_container_width=True):
            try:
                dashboard.trigger_workflow(dashboard.BLOGGER_REPO)
                st.success("실행 시작! 2~3분 뒤 블로그에 새 글이 올라옵니다.")
            except Exception as exc:
                st.error(f"실행 실패: {exc}")
    with col_b:
        if st.button("🎬 유튜브 영상 지금 제작", use_container_width=True):
            try:
                dashboard.trigger_workflow(dashboard.SHORTS_REPO)
                st.success("실행 시작! 5~10분 뒤 유튜브에 업로드됩니다.")
            except Exception as exc:
                st.error(f"실행 실패: {exc}")

    col_c, col_d = st.columns(2)
    with col_c:
        st.button("👻 두 줄 괴담 글 생성", use_container_width=True,
                  on_click=_go_gwidam, args=("two_sentence",))
    with col_d:
        st.button("👻 단편 괴담 글 생성", use_container_width=True,
                  on_click=_go_gwidam, args=("nosleep",))

    _schedule_editor("블로거 자동 발행", dashboard.BLOGGER_REPO, "blogger")
    _schedule_editor("유튜브 자동 업로드", dashboard.SHORTS_REPO, "shorts")

    # ── 애드센스 승인 상태 ─────────────────────────────────
    st.divider()
    st.subheader("🟢 블로거 애드센스")
    ad_status, ad = _metric_block(dashboard.blogger_adsense_status, "m_ad_status")
    if ad_status == "ok":
        state = ad.get("state", "UNKNOWN")
        if ad.get("approved"):
            dday = ad.get("coupang_dday")
            if ad.get("coupang_active_date"):
                if dday is not None and dday > 0:
                    coupang = f"쿠팡 링크 D-{dday} ({ad['coupang_active_date']}부터)"
                else:
                    coupang = "쿠팡 링크 활성 ✅"
            else:
                coupang = "승인 기록 동기화 대기"
            st.success(f"승인 완료 ✅  ·  {coupang}")
        elif state == "GETTING_READY":
            st.warning("심사 중 🟡 (준비 중 — 승인되면 자동 반영)")
        elif state == "REQUIRES_REVIEW":
            st.warning("심사 대기 🟡 (검토 요청됨)")
        elif state == "NEEDS_ATTENTION":
            st.error("확인 필요 🔴 (애드센스에서 조치 필요)")
        else:
            st.info(f"상태: {state}")
    else:
        st.caption(f"상태 조회 실패: {ad}")

    # ── 지표 + 추세 ───────────────────────────────────────
    st.divider()
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.subheader("📈 지표")
    with top_right:
        if st.button("🔄 새로고침", key="dash_refresh", use_container_width=True):
            for k in ("m_blogger", "m_coupang", "m_youtube", "m_adsense",
                      "m_tistory", "m_ad_status", "metrics_recorded"):
                st.session_state.pop(k, None)
            st.rerun()

    s_bl, bl = _metric_block(dashboard.blogger_stats, "m_blogger")
    s_cp, cp = _metric_block(dashboard.coupang_stats, "m_coupang")
    s_yt, yt = _metric_block(dashboard.youtube_stats, "m_youtube")
    s_ad, adr = _metric_block(dashboard.adsense_stats, "m_adsense")
    s_ts, ts = _metric_block(dashboard.tistory_stats, "m_tistory")

    st.markdown("**📝 Blogger — AI공부하는 직장인의 개발 노트**")
    if s_bl == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("총 조회수", f"{bl['views_all']:,}")
        c2.metric("최근 7일", f"{bl['views_7d']:,}")
        c3.metric("발행 글", f"{bl['posts']:,}개")
    else:
        st.caption(f"조회 실패: {bl}")

    st.markdown("**🛒 쿠팡파트너스 (최근 30일)**")
    if s_cp == "ok":
        c1, c2 = st.columns(2)
        c1.metric("클릭", f"{cp['clicks']:,}회")
        c2.metric("수수료", f"{cp['commission']:,.0f}원")
    else:
        st.caption(f"조회 실패: {cp}")

    st.markdown("**🎬 유튜브 — 돈의 흐름 읽기**")
    if s_yt == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("구독자", f"{yt['subscribers']:,}")
        c2.metric("총 조회수", f"{yt['views']:,}")
        c3.metric("영상", f"{yt['videos']:,}개")
    else:
        st.caption(f"조회 실패: {yt}")

    st.markdown("**💰 애드센스 수익**")
    if s_ad == "ok":
        c1, c2, c3 = st.columns(3)
        c1.metric("오늘", f"{adr['today']:,.0f}원")
        c2.metric("최근 7일", f"{adr['last_7d']:,.0f}원")
        c3.metric("이번 달", f"{adr['month']:,.0f}원")
    else:
        st.caption(f"미연결: {adr}")

    st.markdown("**🏠 티스토리 방문자 (GA4)**")
    if s_ts == "ok":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("오늘 방문", f"{ts['today_users']:,}")
        c2.metric("오늘 조회", f"{ts['today_views']:,}")
        c3.metric("7일 방문", f"{ts['week_users']:,}")
        c4.metric("7일 조회", f"{ts['week_views']:,}")
    else:
        st.caption(f"미연결: {ts}")

    # 오늘 지표 스냅샷 기록 (세션당 1회) → 추세 그래프용
    if "metrics_recorded" not in st.session_state:
        snapshot = {}
        if s_bl == "ok":
            snapshot["블로거 조회수"] = bl["views_all"]
        if s_cp == "ok":
            snapshot["쿠팡 수수료"] = cp["commission"]
        if s_yt == "ok":
            snapshot["유튜브 구독자"] = yt["subscribers"]
            snapshot["유튜브 조회수"] = yt["views"]
        if s_ad == "ok":
            snapshot["애드센스 이번달"] = adr["month"]
        if s_ts == "ok":
            snapshot["티스토리 7일방문"] = ts["week_users"]
        if snapshot:
            dashboard.record_metrics_today(snapshot)
        st.session_state["metrics_recorded"] = True

    st.divider()
    st.subheader("📊 추세 (일별)")
    history = dashboard.load_metrics_history()
    if len(history) < 2:
        st.caption("추세는 이틀 이상 데이터가 쌓이면 나타나요. "
                   "매일 이 앱을 한 번씩 열면 그날 지표가 자동 기록됩니다.")
    else:
        try:
            import pandas as pd

            df = pd.DataFrame(history).set_index("date")
            for col in df.columns:
                st.caption(col)
                st.line_chart(df[[col]], height=160)
        except Exception as exc:
            st.caption(f"그래프 표시 실패: {exc}")


# ══════════════════════════════════════════════════════════
# 👻 괴담 (티스토리)
# ══════════════════════════════════════════════════════════

if active_tab == TABS[1]:
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

    # 대시보드 버튼에서 넘어온 자동 실행 (있으면 그 모드로 바로 생성)
    autorun = st.session_state.pop("gwidam_autorun", None)
    default_idx = list(MODE_LABELS).index(autorun) if autorun in MODE_LABELS else 0

    mode = st.radio(
        "모드",
        options=list(MODE_LABELS),
        format_func=MODE_LABELS.get,
        horizontal=True,
        index=default_idx,
    )
    if autorun in MODE_LABELS:
        mode = autorun
        st.info(f"대시보드에서 '{MODE_LABELS[mode]}' 생성을 요청했어요 — 바로 시작합니다.")

    start_number = 0
    if mode == "two_sentence":
        start_number = st.number_input(
            "시작 번호 (0 = 자동, 마지막 번호 다음)", min_value=0, step=1, value=0
        )

    if st.button("⚡ 글 생성", type="primary", use_container_width=True) or autorun:
        with st.status("실행 중…", expanded=True) as status_box:
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
                status_box.update(
                    label="완료! 아래 대기 목록에서 복사하세요", state="complete", expanded=False
                )
            except Exception as exc:
                logger.exception("cloud run failed: %s", exc)
                status_box.update(label="실패", state="error")
                st.error(str(exc))

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
        "티스토리에 올린 뒤 [올렸음]을 누르면 글 데이터가 삭제됩니다 (번호·사용 기록만 유지). "
        "글에 들어간 Reddit 원문은 즉시 기록되어 다시 나오지 않습니다."
    )


# ══════════════════════════════════════════════════════════
# 🎬 유튜브
# ══════════════════════════════════════════════════════════

if active_tab == TABS[2]:
    status, data = _metric_block(dashboard.youtube_stats, "m_youtube")
    if status == "ok":
        st.subheader(f"채널: {data['channel']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("구독자", f"{data['subscribers']:,}")
        c2.metric("총 조회수", f"{data['views']:,}")
        c3.metric("영상", f"{data['videos']:,}개")
    else:
        st.caption(f"채널 정보를 불러오지 못했어요: {data}")

    st.divider()
    if st.button("🎬 지금 영상 제작 + 업로드", type="primary", use_container_width=True):
        try:
            dashboard.trigger_workflow(dashboard.SHORTS_REPO)
            st.success("실행 시작! 5~10분 뒤 유튜브 채널에 새 영상이 올라옵니다.")
        except Exception as exc:
            st.error(f"실행 실패: {exc}")

    _schedule_editor("자동 업로드", dashboard.SHORTS_REPO, "shorts_tab")

    shorts_app = dashboard._secret("SHORTS_APP_URL")
    if shorts_app:
        st.link_button("🎛️ 영상 미리보기·다운로드 앱 열기", shorts_app, use_container_width=True)
