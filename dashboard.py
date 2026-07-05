# -*- coding: utf-8 -*-
"""파이프라인 HQ 대시보드 — 지표 조회 + 원격 조종.

지표 (전부 공식 API):
- Blogger 조회수 (pageviews API)
- 쿠팡파트너스 실적 (commission report API)
- 유튜브 채널 통계 (YouTube Data API)

원격 조종 (GitHub API):
- blogger-auto / market-shorts 저장소의 schedule.json 조회·수정
- 워크플로우 즉시 실행 (지금 글 발행 / 지금 영상 제작)

인증값 우선순위: Streamlit secrets → 환경변수 → 로컬 파일(PC 테스트용)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).parent
BLOGGER_BLOG_ID = "1209531061110390976"
BLOGGER_REPO = "hyjh1006-afk/blogger-auto"
SHORTS_REPO = "hyjh1006-afk/market-shorts"

# 로컬 테스트용 파일 위치 (클라우드에는 없음 — secrets 사용)
_LOCAL_BLOGGER_TOKEN = ROOT.parent / "Blogger_auto" / "token.json"
_LOCAL_COUPANG_KEYS = ROOT.parent / "Blogger_auto" / "coupang_keys.txt"
_LOCAL_YT_TOKEN = ROOT.parent.parent / "ai" / "content_factory" / "token.json"


def _secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st

        value = str(st.secrets.get(name, "")).strip()
        if value:
            return value
    except Exception:
        pass
    import os

    return os.environ.get(name, default).strip()


# ── 구글 OAuth 공통 ─────────────────────────────────────────

def _google_access_token(prefix: str, local_token_path: Path) -> str:
    """prefix: 'BLOGGER' 또는 'YT' — secrets에서 읽고, 없으면 로컬 token.json"""
    client_id = _secret(f"{prefix}_CLIENT_ID")
    client_secret = _secret(f"{prefix}_CLIENT_SECRET")
    refresh_token = _secret(f"{prefix}_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token) and local_token_path.exists():
        data = json.loads(local_token_path.read_text(encoding="utf-8"))
        client_id = data.get("client_id", "")
        client_secret = data.get("client_secret", "")
        refresh_token = data.get("refresh_token", "")
    if not (client_id and client_secret and refresh_token):
        raise RuntimeError(f"{prefix} 인증값이 없습니다 (secrets 설정 필요)")

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


# ── Blogger 지표 ────────────────────────────────────────────

def blogger_stats() -> dict:
    token = _google_access_token("BLOGGER", _LOCAL_BLOGGER_TOKEN)
    headers = {"Authorization": f"Bearer {token}"}

    views = requests.get(
        f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/pageviews",
        headers=headers,
        params={"range": ["all", "7DAYS"]},
        timeout=30,
    )
    views.raise_for_status()
    counts = {c["timeRange"]: int(c["count"]) for c in views.json().get("counts", [])}

    blog = requests.get(
        f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}",
        headers=headers,
        timeout=30,
    )
    blog.raise_for_status()
    info = blog.json()

    return {
        "views_all": counts.get("ALL_TIME", 0),
        "views_7d": counts.get("SEVEN_DAYS", 0),
        "posts": int(info.get("posts", {}).get("totalItems", 0)),
        "url": info.get("url", ""),
    }


# ── 쿠팡파트너스 실적 ───────────────────────────────────────

_COUPANG_DOMAIN = "https://api-gateway.coupang.com"


def _coupang_keys() -> tuple[str, str] | None:
    access = _secret("COUPANG_ACCESS_KEY")
    secret = _secret("COUPANG_SECRET_KEY")
    if access and secret:
        return access, secret
    if _LOCAL_COUPANG_KEYS.exists():
        lines = [
            line.strip()
            for line in _LOCAL_COUPANG_KEYS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(lines) >= 2:
            return lines[0], lines[1]
    return None


def coupang_stats(days: int = 30) -> dict:
    keys = _coupang_keys()
    if not keys:
        raise RuntimeError("쿠팡 키가 없습니다 (secrets 설정 필요)")
    access, secret = keys

    path = "/v2/providers/affiliate_open_api/apis/openapi/reports/commission"
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=days - 1)).strftime("%Y%m%d")
    query = f"startDate={start}&endDate={end}"

    signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    message = signed_date + "GET" + path + query
    signature = hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    auth = (
        f"CEA algorithm=HmacSHA256, access-key={access}, "
        f"signed-date={signed_date}, signature={signature}"
    )

    response = requests.get(
        f"{_COUPANG_DOMAIN}{path}?{query}",
        headers={"Authorization": auth},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json().get("data") or []
    return {
        "clicks": sum(int(r.get("click") or 0) for r in rows),
        "commission": float(sum(float(r.get("commission") or 0) for r in rows)),
        "days": days,
    }


# ── 유튜브 채널 통계 ────────────────────────────────────────

def youtube_stats() -> dict:
    token = _google_access_token("YT", _LOCAL_YT_TOKEN)
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        headers={"Authorization": f"Bearer {token}"},
        params={"part": "snippet,statistics", "mine": "true"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items") or []
    if not items:
        raise RuntimeError("유튜브 채널을 찾지 못했습니다")
    channel = items[0]
    stats = channel.get("statistics", {})
    return {
        "channel": channel.get("snippet", {}).get("title", ""),
        "subscribers": int(stats.get("subscriberCount") or 0),
        "views": int(stats.get("viewCount") or 0),
        "videos": int(stats.get("videoCount") or 0),
    }


# ── 애드센스 수익 (AdSense Management API) ──────────────────

_LOCAL_STAGE2_TOKEN = ROOT / "stage2_token.json"


def _stage2_access_token() -> str:
    """애드센스+GA4 겸용 토큰 (scope: adsense.readonly, analytics.readonly)"""
    client_id = _secret("BLOGGER_CLIENT_ID")
    client_secret = _secret("BLOGGER_CLIENT_SECRET")
    refresh_token = _secret("REPORTS_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token) and _LOCAL_STAGE2_TOKEN.exists():
        data = json.loads(_LOCAL_STAGE2_TOKEN.read_text(encoding="utf-8"))
        client_id = client_id or data.get("client_id", "")
        client_secret = client_secret or data.get("client_secret", "")
        refresh_token = data.get("refresh_token", "")
    if not (client_id and client_secret and refresh_token):
        raise RuntimeError("애드센스/GA 토큰이 없습니다 (get_stage2_token.py 실행 필요)")
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def adsense_stats() -> dict:
    token = _stage2_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    accounts = requests.get(
        "https://adsense.googleapis.com/v2/accounts", headers=headers, timeout=30
    )
    accounts.raise_for_status()
    items = accounts.json().get("accounts") or []
    if not items:
        raise RuntimeError("애드센스 계정을 찾지 못했습니다")
    account = items[0]["name"]  # accounts/pub-xxxx

    def _earnings(date_range: str) -> float:
        report = requests.get(
            f"https://adsense.googleapis.com/v2/{account}/reports:generate",
            headers=headers,
            params={
                "dateRange": date_range,
                "metrics": "ESTIMATED_EARNINGS",
                "reportingTimeZone": "ACCOUNT_TIME_ZONE",
            },
            timeout=30,
        )
        report.raise_for_status()
        totals = report.json().get("totals", {}).get("cells", [])
        return float(totals[0].get("value") or 0) if totals else 0.0

    return {
        "today": _earnings("TODAY"),
        "last_7d": _earnings("LAST_7_DAYS"),
        "month": _earnings("MONTH_TO_DATE"),
        "account": account.replace("accounts/", ""),
    }


# ── 티스토리 방문자 (GA4 Data API) ──────────────────────────

def tistory_stats() -> dict:
    property_id = _secret("GA4_PROPERTY_ID")
    if not property_id and _LOCAL_STAGE2_TOKEN.exists():
        property_id = json.loads(
            _LOCAL_STAGE2_TOKEN.read_text(encoding="utf-8")
        ).get("ga4_property_id", "")
    if not property_id:
        raise RuntimeError("GA4_PROPERTY_ID가 없습니다 (GA4 설치 후 설정)")

    token = _stage2_access_token()

    def _report(start: str) -> dict:
        response = requests.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "dateRanges": [{"startDate": start, "endDate": "today"}],
                "metrics": [{"name": "activeUsers"}, {"name": "screenPageViews"}],
            },
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json().get("rows") or []
        if not rows:
            return {"users": 0, "views": 0}
        values = rows[0].get("metricValues", [])
        return {
            "users": int(values[0].get("value") or 0) if values else 0,
            "views": int(values[1].get("value") or 0) if len(values) > 1 else 0,
        }

    today = _report("today")
    week = _report("7daysAgo")
    return {
        "today_users": today["users"],
        "today_views": today["views"],
        "week_users": week["users"],
        "week_views": week["views"],
    }


# ── GitHub 원격 조종 (시간표·즉시 실행) ─────────────────────

_GH_API = "https://api.github.com"


def _gh_headers() -> dict:
    token = _secret("HQ_GITHUB_TOKEN") or _secret("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub 토큰이 없습니다")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_schedule(repo: str) -> tuple[list[str], str]:
    """(times 목록, 파일 sha)"""
    response = requests.get(
        f"{_GH_API}/repos/{repo}/contents/schedule.json",
        headers=_gh_headers(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
    return [str(t) for t in data.get("times", [])], payload["sha"]


def save_schedule(repo: str, times: list[str], sha: str) -> None:
    current = requests.get(
        f"{_GH_API}/repos/{repo}/contents/schedule.json",
        headers=_gh_headers(),
        timeout=20,
    )
    current.raise_for_status()
    data = json.loads(base64.b64decode(current.json()["content"]).decode("utf-8"))
    data["times"] = times[:6]

    bot = {
        "name": "pipeline-hq",
        "email": "287627535+hyjh1006-afk@users.noreply.github.com",
    }
    response = requests.put(
        f"{_GH_API}/repos/{repo}/contents/schedule.json",
        headers=_gh_headers(),
        json={
            "message": f"시간표 변경: {', '.join(times) or '(비움)'}",
            "content": base64.b64encode(
                (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).decode("ascii"),
            "sha": current.json()["sha"],
            "committer": bot,
            "author": bot,
        },
        timeout=20,
    )
    response.raise_for_status()


def blogger_adsense_status() -> dict:
    """블로거 애드센스 승인 상태 + 쿠팡 링크 활성 시점.
    반환: {state, approved: bool, approved_date, coupang_active_date, coupang_dday}"""
    result = {
        "state": "UNKNOWN",
        "approved": False,
        "approved_date": "",
        "coupang_active_date": "",
        "coupang_dday": None,
    }
    # 1) 애드센스 API로 현재 사이트 상태
    try:
        token = _stage2_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        acc = requests.get(
            "https://adsense.googleapis.com/v2/accounts", headers=headers, timeout=30
        ).json()
        account = acc["accounts"][0]["name"]
        sites = requests.get(
            f"https://adsense.googleapis.com/v2/{account}/sites",
            headers=headers,
            timeout=30,
        ).json()
        for site in sites.get("sites", []):
            dom = site.get("domain", "").replace("www.", "").lower()
            if "afterwork-ai" in dom:
                result["state"] = site.get("state", "UNKNOWN")
                result["approved"] = site.get("state") == "READY"
                break
    except Exception:
        pass

    # 2) blogger-auto가 기록한 승인일 → 쿠팡 활성 D-day
    try:
        from datetime import date, timedelta

        r = requests.get(
            f"{_GH_API}/repos/{BLOGGER_REPO}/contents/state/adsense_status.json",
            headers=_gh_headers(),
            timeout=20,
        )
        if r.status_code == 200:
            data = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
            approved = data.get("approved_date", "")
            if approved:
                result["approved_date"] = approved
                active = date.fromisoformat(approved) + timedelta(days=30)
                result["coupang_active_date"] = active.isoformat()
                result["coupang_dday"] = (active - date.today()).days
    except Exception:
        pass
    return result


METRICS_HISTORY_PATH = "state/metrics_history.json"


def load_metrics_history() -> list[dict]:
    try:
        r = requests.get(
            f"{_GH_API}/repos/{_secret('STATE_REPO')}/contents/{METRICS_HISTORY_PATH}",
            headers=_gh_headers(),
            params={"ref": _secret("STATE_BRANCH", "main")},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
    except Exception:
        return []


def record_metrics_today(metrics: dict) -> None:
    """오늘(KST) 지표를 히스토리에 upsert (하루 1행). 실패해도 조용히 무시."""
    from datetime import datetime, timezone, timedelta

    today = (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()
    repo = _secret("STATE_REPO")
    branch = _secret("STATE_BRANCH", "main")
    try:
        r = requests.get(
            f"{_GH_API}/repos/{repo}/contents/{METRICS_HISTORY_PATH}",
            headers=_gh_headers(),
            params={"ref": branch},
            timeout=20,
        )
        history, sha = [], None
        if r.status_code == 200:
            sha = r.json()["sha"]
            history = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        row = {"date": today, **metrics}
        history = [h for h in history if h.get("date") != today] + [row]
        history = history[-60:]  # 최근 60일만

        bot = {"name": "pipeline-hq",
               "email": "287627535+hyjh1006-afk@users.noreply.github.com"}
        body = {
            "message": f"지표 기록 {today}",
            "content": base64.b64encode(
                json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8")
            ).decode("ascii"),
            "branch": branch,
            "committer": bot,
            "author": bot,
        }
        if sha:
            body["sha"] = sha
        requests.put(
            f"{_GH_API}/repos/{repo}/contents/{METRICS_HISTORY_PATH}",
            headers=_gh_headers(),
            json=body,
            timeout=20,
        )
    except Exception:
        pass


def trigger_workflow(repo: str, workflow_file: str = "daily.yml") -> None:
    """워크플로우 즉시 실행 (지금 글 발행 / 지금 영상 제작·업로드)"""
    response = requests.post(
        f"{_GH_API}/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
        headers=_gh_headers(),
        json={"ref": "main"},
        timeout=20,
    )
    response.raise_for_status()
