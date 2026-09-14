#!/bin/bash
# 대기 목록의 괴담(두 줄·단편)을 티스토리에 「비공개 저장」한다 — 클로드 토큰 0.
# 번역은 루틴(클로드)이 하고, 편집기 클릭은 전부 이 스크립트가 한다.
#
# 사용: scripts/publish_waiting.sh [--dry-run] [--fixture <글.json>]
#   --dry-run          저장 버튼 직전까지 전부 하고 스크린샷(logs/)만 남긴 뒤 버린다.
#   --fixture <json>   state/local_outputs 형식 파일로 시험(제목 앞에 [DRYRUN-TEST] 붙음). 항상 dry-run.
#
# 종료 코드
#   0  정상 (올릴 것 없음 포함)
#   1  게이트 실패 — 아무것도 저장 안 함 (제목·본문 길이·비공개·카테고리·태그 불일치, 편집기 이상)
#   2  Aside 가 안 뜸 / repl 무응답
#   4  티스토리 로그인 풀림 (간편로그인은 SKILL 1단계 절차, 비밀번호 입력은 사람 몫)
#   5  저장 버튼은 눌렀는데 확인 못 함 — 사람이 /manage/posts/ 확인. 재시도 금지
#      (다음 실행은 같은 제목이 이미 있으면 다시 올리지 않고 대기 목록만 정리한다)
#   7  CAPTCHA — 편집기 탭을 그대로 열어 둠. 사람이 풀면 저장된다. 자동으로 풀지 않는다
#   8  편집기 잠금(/tmp/tistory-editor.lock) 또는 다른 편집기 탭이 10분 넘게 사용 중
#
# 안전장치: 공개 발행 절대 없음(비공개 라디오·버튼 문구를 클릭 직전 같은 틱에서 재확인),
# 자동저장 슬롯 오염 방지(우리 탭의 /manage/autosave POST 차단 + 끝에 원래 상태로 복원).
set -euo pipefail
ROOT="/Users/oddo/Developer/oddo/Tistory_cloud"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export STATE_REPO="hyjh1006-afk/tistory-cloud"
export STATE_BRANCH="main"
GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"; export GITHUB_TOKEN
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/publish_waiting.py" "$@"
