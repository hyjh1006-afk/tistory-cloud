"""번호/사용 기록을 GitHub 저장소에 보존.

Streamlit Cloud는 재시작하면 로컬 파일이 초기화되므로,
앱 시작 시 GitHub에서 상태를 내려받고(pull) 글 생성 성공 후 올린다(push).

secrets 필요: GITHUB_TOKEN, STATE_REPO (예: "username/tistory-cloud"), STATE_BRANCH(선택, 기본 main)
secrets가 없으면 로컬 파일만 사용 (PC에서 테스트할 때).
"""

from __future__ import annotations

import base64
from pathlib import Path

import requests

from src.paths import LAST_NUMBER_PATH, REDDIT_DAILY_PATH, ROOT_DIR, USED_POSTS_PATH

# last_output.json: 마지막으로 생성한 글(HTML 포함) — 폰이 결과 화면을 놓쳐도 복구 가능
LAST_OUTPUT_PATH = ROOT_DIR / "last_output.json"

STATE_FILES: dict[str, Path] = {
    "state/last_number.json": LAST_NUMBER_PATH,
    "state/used_posts.json": USED_POSTS_PATH,
    "state/reddit_daily.json": REDDIT_DAILY_PATH,
    "state/last_output.json": LAST_OUTPUT_PATH,
}

API_BASE = "https://api.github.com"


def _settings() -> tuple[str, str, str] | None:
    try:
        import streamlit as st

        token = str(st.secrets.get("GITHUB_TOKEN", "")).strip()
        repo = str(st.secrets.get("STATE_REPO", "")).strip()
        branch = str(st.secrets.get("STATE_BRANCH", "main")).strip() or "main"
    except Exception:
        return None
    if not token or not repo:
        return None
    return token, repo, branch


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def enabled() -> bool:
    return _settings() is not None


def pull_state() -> str:
    """GitHub → 로컬. 성공/생략 메시지를 돌려준다."""
    settings = _settings()
    if not settings:
        return "GitHub 미설정 — 로컬 상태 사용"
    token, repo, branch = settings

    pulled = 0
    for repo_path, local_path in STATE_FILES.items():
        url = f"{API_BASE}/repos/{repo}/contents/{repo_path}"
        response = requests.get(
            url, headers=_headers(token), params={"ref": branch}, timeout=20
        )
        if response.status_code == 404:
            continue
        response.raise_for_status()
        content = base64.b64decode(response.json()["content"]).decode("utf-8")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        pulled += 1
    return f"GitHub 상태 동기화 완료 ({pulled}개 파일)"


def push_state() -> str:
    """로컬 → GitHub."""
    settings = _settings()
    if not settings:
        return "GitHub 미설정 — 로컬에만 저장됨"
    token, repo, branch = settings

    pushed = 0
    for repo_path, local_path in STATE_FILES.items():
        if not local_path.exists():
            continue
        url = f"{API_BASE}/repos/{repo}/contents/{repo_path}"

        sha = None
        current = requests.get(
            url, headers=_headers(token), params={"ref": branch}, timeout=20
        )
        if current.status_code == 200:
            sha = current.json().get("sha")

        body = {
            "message": f"update {repo_path}",
            "content": base64.b64encode(
                local_path.read_text(encoding="utf-8").encode("utf-8")
            ).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        response = requests.put(url, headers=_headers(token), json=body, timeout=20)
        response.raise_for_status()
        pushed += 1
    return f"GitHub에 상태 저장 완료 ({pushed}개 파일)"
