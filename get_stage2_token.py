# -*- coding: utf-8 -*-
"""최초 1회 실행: 구글 로그인 → 애드센스 수익 조회 권한 토큰 생성.

준비물:
1. 구글 클라우드 콘솔에서 AdSense Management API 사용 설정
2. Blogger_auto 폴더의 client_secret.json 재사용 (자동으로 찾음)

실행: python get_stage2_token.py
→ 브라우저 로그인 (⚠️ 애드센스가 연결된 구글 계정으로!)
→ stage2_token.json 생성 + Streamlit secrets에 넣을 값 출력
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
CLIENT_SECRET = BASE.parent / "Blogger_auto" / "client_secret.json"
TOKEN = BASE / "stage2_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/adsense.readonly",
]


def main() -> None:
    if not CLIENT_SECRET.exists():
        print(f"client_secret.json을 찾지 못했습니다: {CLIENT_SECRET}")
        raise SystemExit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    secret = json.loads(CLIENT_SECRET.read_text(encoding="utf-8"))
    installed = secret.get("installed") or secret.get("web") or {}
    TOKEN.write_text(
        json.dumps(
            {
                "client_id": installed.get("client_id", ""),
                "client_secret": installed.get("client_secret", ""),
                "refresh_token": creds.refresh_token,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"완료! {TOKEN} 생성됨.")
    print()
    print("Streamlit secrets에 추가할 값:")
    print("  REPORTS_REFRESH_TOKEN = (stage2_token.json의 refresh_token 값)")


if __name__ == "__main__":
    main()
