"""번호/사용 기록을 GitHub 저장소에 보존.

Streamlit Cloud는 재시작하면 로컬 파일이 초기화되므로,
앱 시작 시 GitHub에서 상태를 내려받고(pull) 글 생성 성공 후 올린다(push).

secrets 필요: GITHUB_TOKEN, STATE_REPO (예: "username/tistory-cloud"), STATE_BRANCH(선택, 기본 main)
secrets가 없으면 로컬 파일만 사용 (PC에서 테스트할 때).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import requests

from src.paths import LAST_NUMBER_PATH, REDDIT_DAILY_PATH, USED_POSTS_PATH

STATE_FILES: dict[str, Path] = {
    "state/last_number.json": LAST_NUMBER_PATH,
    "state/used_posts.json": USED_POSTS_PATH,
    "state/reddit_daily.json": REDDIT_DAILY_PATH,
}

# 대기 중인 글 (생성됐지만 아직 티스토리에 안 올린 글들)
OUTPUTS_DIR = "state/outputs"

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

        # committer를 명시하지 않으면 계정 이메일이 공개 커밋에 노출된다
        bot_identity = {
            "name": "tistory-cloud-bot",
            "email": "287627535+hyjh1006-afk@users.noreply.github.com",
        }
        body = {
            "message": f"update {repo_path}",
            "content": base64.b64encode(
                local_path.read_text(encoding="utf-8").encode("utf-8")
            ).decode("ascii"),
            "branch": branch,
            "committer": bot_identity,
            "author": bot_identity,
        }
        if sha:
            body["sha"] = sha

        response = requests.put(url, headers=_headers(token), json=body, timeout=20)
        response.raise_for_status()
        pushed += 1
    return f"GitHub에 상태 저장 완료 ({pushed}개 파일)"


def _bot_identity() -> dict[str, str]:
    return {
        "name": "tistory-cloud-bot",
        "email": "287627535+hyjh1006-afk@users.noreply.github.com",
    }


def list_outputs() -> list[dict]:
    """대기 중인 글 목록 (오래된 것부터 — 올릴 순서대로)."""
    settings = _settings()
    if not settings:
        return []
    token, repo, branch = settings

    listing = requests.get(
        f"{API_BASE}/repos/{repo}/contents/{OUTPUTS_DIR}",
        headers=_headers(token),
        params={"ref": branch},
        timeout=20,
    )
    if listing.status_code == 404:
        return []
    listing.raise_for_status()

    outputs = []
    for entry in sorted(listing.json(), key=lambda e: e.get("name", "")):
        if not entry.get("name", "").endswith(".json"):
            continue
        detail = requests.get(
            entry["url"], headers=_headers(token), timeout=20
        )
        if detail.status_code != 200:
            continue
        try:
            data = json.loads(
                base64.b64decode(detail.json()["content"]).decode("utf-8")
            )
        except (ValueError, KeyError):
            continue
        data["_name"] = entry["name"]
        data["_sha"] = entry["sha"]
        outputs.append(data)
    return outputs


def save_output(name: str, data: dict) -> None:
    """생성된 글을 대기 목록에 저장."""
    settings = _settings()
    if not settings:
        return
    token, repo, branch = settings
    body = {
        "message": f"글 생성: {name}",
        "content": base64.b64encode(
            json.dumps(data, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
        "branch": branch,
        "committer": _bot_identity(),
        "author": _bot_identity(),
    }
    response = requests.put(
        f"{API_BASE}/repos/{repo}/contents/{OUTPUTS_DIR}/{name}",
        headers=_headers(token),
        json=body,
        timeout=20,
    )
    response.raise_for_status()


def delete_output(name: str, sha: str) -> None:
    """올린 글을 대기 목록에서 제거."""
    settings = _settings()
    if not settings:
        return
    token, repo, branch = settings
    response = requests.delete(
        f"{API_BASE}/repos/{repo}/contents/{OUTPUTS_DIR}/{name}",
        headers=_headers(token),
        json={
            "message": f"올림 완료: {name}",
            "sha": sha,
            "branch": branch,
            "committer": _bot_identity(),
            "author": _bot_identity(),
        },
        timeout=20,
    )
    response.raise_for_status()
