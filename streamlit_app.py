"""🎛️ 파이프라인 HQ — 읽기 전용 지표 대시보드.

플랫폼별 **자동발행 시간 · 조회수 · 수익 · 방문자**를 한 화면에서 확인만 한다.
발행 버튼·시간표 편집·괴담 생성 탭은 2026-09-05 제거(사용자 지시) —
"걍 플랫폼별로 자동발행시간이랑 조회수·수익·방문자 쭉 확인이나 되면 됨".
자동 발행 자체는 각 저장소의 GitHub Actions / 예약작업이 알아서 돈다.
"""

import streamlit as st

st.set_page_config(page_title="파이프라인 HQ", page_icon="🎛️", layout="centered")


# ── PIN 잠금 (모아이 랩과 같은 PIN) ─────────────────────────
def _require_pin() -> None:
    try:
        pin = str(st.secrets.get("HQ_PIN", "")).strip()
    except Exception:
        pin = ""
    if not pin:
        st.error(
            "🔒 PIN이 설정되지 않았습니다.\n\n"
            "Streamlit Cloud → Settings → Secrets 에 `HQ_PIN = \"...\"` 한 줄을 추가하세요."
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

st.title("🎛️ 파이프라인 HQ")
st.caption("읽기 전용 관제 · 플랫폼별 자동발행 시간 · 조회수 · 수익 · 방문자")

if st.button("🔄 새로고침", use_container_width=True):
    for k in list(st.session_state.keys()):
        if k.startswith("m_"):
            st.session_state.pop(k, None)
    st.rerun()


def _metric_block(loader, cache_key: str):
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = ("ok", loader())
        except Exception as exc:
            st.session_state[cache_key] = ("err", str(exc))
    return st.session_state[cache_key]


def _sched_caption(repo: str) -> None:
    """저장소 schedule.json 을 읽어 자동발행 시간을 '보여주기만' 한다(편집 불가)."""
    try:
        slots, _ = dashboard.get_schedule(repo)
        parts = " · ".join(
            f"{n} {', '.join(t)}" for n, t in slots.items()
        ) if slots else "(꺼짐)"
        st.caption(f"⏰ 자동발행 {parts} · 한국시간")
    except Exception:
        pass


# ── 지표 로드 (세션 캐시) ───────────────────────────────────
s_sp, sp = _metric_block(dashboard.space_shorts_stats, "m_space")
s_yt, yt = _metric_block(dashboard.youtube_stats, "m_youtube")
s_ki, kitchen = _metric_block(dashboard.kitchen_stats, "m_kitchen")
s_bl, bl = _metric_block(dashboard.blogger_stats, "m_blogger")
s_cp, cp = _metric_block(dashboard.coupang_stats, "m_coupang")
s_ad, adr = _metric_block(dashboard.adsense_stats, "m_adsense")
s_toss, toss = _metric_block(dashboard.toss_ads_stats, "m_toss_ads")


# ══ 🚀 우주쇼츠 (4개 플랫폼) ═══════════════════════════════
st.subheader("🚀 우주쇼츠 — 우주를 여행하는 히키코모리")
if s_sp == "ok":
    c1, c2, c3 = st.columns(3)
    c1.metric("YouTube 구독", f"{sp.get('subs', 0):,}")
    c2.metric("YouTube 총조회", f"{sp.get('views', 0):,}")
    c3.metric("영상", f"{sp.get('video_count', 0):,}개")
    plats = sp.get("platforms") or []
    if plats:
        st.dataframe(
            [{"플랫폼": p["name"], "핸들": p.get("handle", ""), "지표": p.get("metric", "")} for p in plats],
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("유튜브·인스타 @space_hikikomori · 틱톡 @space_hiki · 네이버클립 @space_hikikomori")
    st.caption(
        f"⏰ 자동발행 {' · '.join(dashboard.SPACE_SLOTS)} · 하루 {len(dashboard.SPACE_SLOTS)}편 · "
        f"갱신 {sp.get('updated_at', '')[:16].replace('T', ' ')} "
        "· 인스타/틱톡/네이버 조회수는 공개 API가 없어 스냅샷(space-shorts 세션이 갱신)"
    )
else:
    st.caption(f"조회 실패: {sp}")

# ══ 🎬 돈의 흐름 읽기 (유튜브) ═════════════════════════════
st.subheader("🎬 돈의 흐름 읽기 — 유튜브")
if s_yt == "ok":
    c1, c2, c3 = st.columns(3)
    c1.metric("구독자", f"{yt['subscribers']:,}")
    c2.metric("총 조회수", f"{yt['views']:,}")
    c3.metric("영상", f"{yt['videos']:,}개")
    _sched_caption(dashboard.SHORTS_REPO)
else:
    st.caption(f"조회 실패: {yt}")

# ══ 👻 괴담 — 티스토리 ═════════════════════════════════════
st.subheader("👻 괴담 — 티스토리")
st.caption(
    "⏰ 자동발행 매일 18:26 (예약작업 gwidam-daily-post) · "
    "방문자·조회수는 티스토리가 공개 API를 안 줘서 미연결 · 수익은 아래 애드센스에서 tistory 사이트로 확인"
)
st.caption("[tester188.tistory.com — 새벽 3시의 아카이브](https://tester188.tistory.com/)")

# ══ 🍚 집밥 — Bluesky ══════════════════════════════════════
st.subheader("🍚 집밥 — Bluesky @pparkzze")
if s_ki == "ok":
    bsky = kitchen["bluesky"]
    c1, c2, c3 = st.columns(3)
    c1.metric("팔로워", f"{bsky['followers']:,}")
    c2.metric("전체 글", f"{bsky['posts']:,}개")
    c3.metric("반응", f"{bsky['engagements']:,}건")
    _sched_caption(dashboard.KITCHEN_REPO)
    st.caption("조회수는 Bluesky가 공개 안 함 — 좋아요·재게시·답글·인용만 실측")
else:
    st.caption(f"조회 실패: {kitchen}")

# ══ 📝 Blogger (운영 종료) ═════════════════════════════════
st.subheader("📝 Blogger (운영 종료)")
if s_bl == "ok":
    c1, c2, c3 = st.columns(3)
    c1.metric("총 조회수", f"{bl['views_all']:,}")
    c2.metric("최근 7일", f"{bl['views_7d']:,}")
    c3.metric("발행 글", f"{bl['posts']:,}개")
    st.caption("2026-09-01 운영 종료 — 자동발행 꺼짐, 공개 글은 유지")
else:
    st.caption(f"조회 실패: {bl}")

# ══ 📱 토스 미니앱 — 인앱 광고 ════════════════════════════
st.subheader("📱 토스 미니앱 — 인앱 광고")
if s_toss == "ok":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("출시", f"{toss['released']}/{toss['total_apps']}개")
    c2.metric("총 유저", f"{toss['total_users']:,}", f"+{toss['users_delta']}")
    c3.metric("광고 노출", f"{toss['impressions']:,}회")
    c4.metric("예상 수익", f"{toss['estimated_revenue_krw']:,}원")
    earning = [a for a in toss["apps"] if a["impressions"] > 0]
    if earning:
        st.dataframe(
            [
                {
                    "앱": a["name"],
                    "형태": a["type"],
                    "노출": f"{a['impressions']:,}회",
                    "1천회 단가": f"{a['cpm_krw']:,}원",
                    "예상 수익": f"{a['revenue_krw']:,}원",
                }
                for a in earning
            ],
            hide_index=True, use_container_width=True,
        )
    pending = toss.get("pending_review") or []
    bits = [f"수수료 {toss['commission_rate']}", f"문의 {toss['open_inquiries']}건"]
    if pending:
        bits.append("검토 중 " + ", ".join(pending))
    st.caption(
        f"{toss['updated_at']} 기준 · " + " · ".join(bits)
        + " · 예상 수익은 콘솔 추정값이라 정산 확정 금액과 다를 수 있어요."
    )
    if toss.get("dashboard_url"):
        st.caption(f"[미니앱 관제 페이지 열기]({toss['dashboard_url']})")
else:
    st.caption(f"조회 실패: {toss}")

# ══ 💰 수익 — 쿠팡 · 애드센스 ═════════════════════════════
st.subheader("💰 수익 — 쿠팡파트너스 · 애드센스")
st.markdown("**🛒 쿠팡파트너스 (최근 30일)**")
if s_cp == "ok":
    c1, c2 = st.columns(2)
    c1.metric("클릭", f"{cp['clicks']:,}회")
    c2.metric("수수료", f"{cp['commission']:,.0f}원")
else:
    st.caption(f"조회 실패: {cp}")

st.markdown("**💵 애드센스 (계정 통화 USD)**")
if s_ad == "ok":
    c1, c2, c3 = st.columns(3)
    c1.metric("오늘", f"${adr['today']:,.2f}")
    c2.metric("최근 7일", f"${adr['last_7d']:,.2f}")
    c3.metric("이번 달", f"${adr['month']:,.2f}")
    sites = adr.get("sites") or []
    if sites:
        st.dataframe(
            [{"사이트": x["domain"], "이번 달": f"${x['earnings']:,.2f}", "페이지뷰": f"{x['views']:,}"} for x in sites],
            hide_index=True, use_container_width=True,
        )
    if adr.get("unpaid"):
        st.caption(f"아직 못 받은 돈 **{adr['unpaid']}** — 지급 기준 $100 을 넘으면 통장으로 들어와요.")
else:
    st.caption(f"미연결: {adr}")
