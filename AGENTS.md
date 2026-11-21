# Tistory_cloud

> 🌐 **브라우저는 `mcp__aside__repl` 로 몬다.** 도구 목록에 `aside` 가 안 보이면 없는 게 아니라 deferred 다 —
> **맨 먼저 `ToolSearch(query="select:mcp__aside__repl")`** 로 불러온 뒤 `snapshot()`·`locator`·`getByRole`·`evaluate` 로
> DOM 을 직접 다룬다. `aside repl` CLI·`aside.sh`(CDP)는 셸 배치 스크립트 안에서만(그 경로는 승인창 없이 도는 이점이 있다).
> **좌표 클릭은 쓰지 않는다.** 스크린샷은 조작 수단이 아니라 ①막혔을 때 진단 ②캡챠를 사람에게 넘길 때만 —
> MCP 에서는 `display(await page.screenshot())` 한 줄이면 파일 저장·Read 왕복이 없다.
> 티스토리 편집기 조작법(제목은 진짜 입력, 본문은 합성 paste 등)은 `~/.claude/rules/aside-browser.md` 「티스토리 편집기」 절.
## 무엇
- 티스토리 괴담 원고 생성·연재 도구.
- 🪦 Streamlit 파이프라인 HQ(gwidam-maker.streamlit.app)는 **2026-10-07 폐지·앱 삭제**했다 — 지표는 수익화랩(lab-cloud)이 매일 21:00 모은다. HQ 를 되살리지 않는다.
## 핵심 명령
- 연재 HTML 생성: `bash scripts/cedar.sh build <입력.txt>`.
- 괴담 생성 래퍼: `bash scripts/gwidam.sh two_sentence` 또는 `bash scripts/gwidam.sh nosleep`.
## 구조·진입점
- `github_state.py`·`state/`: 공유 상태(괴담 스크립트가 쓴다 — HQ 와 함께 지우지 말 것). `state/toss_ads.json` 은 수익화랩이 매일 읽는다.
- `scripts/`: 생성·연재 도구, `src/`: 생성 로직, `cedar/`: 연재 자료, `output/`: 생성물.
- 인증 정보는 환경변수·로컬 비밀 파일로 관리한다. 값은 기록하지 않는다(코드의 `st.secrets` 폴백은 HQ 시절 잔재로, 없으면 조용히 건너뛴다).
## 업로드 뒤 용량 정리 (항상 — 2026-11-13 대표님)
- 블로그에 올라갔으면 **삽화(`assets/illustrations/`)·번역 원고(`cedar/<ep>.txt`·`*_src/`)·`state/local_outputs/`·GitHub 대기 목록(`state/outputs/`)은 지운다. 백업 안 남긴다.**
- `cedar_post.sh` 는 발행 확인 뒤 자기 편 것을 알아서 지운다(남기려면 `CEDAR_KEEP=1`). 괴담 자동발행은 `publish_waiting.sh` → `cleanup_posted.sh` 가 한다.
- 손으로 올렸거나 정리가 빠졌으면: 블로그에 있는지 posts.json 으로 확인 → 위 파일 삭제 + `scripts/list_waiting.sh | cut -f1 | xargs scripts/mark_posted.sh`(zsh 는 `$names` 를 안 쪼갠다 — xargs 로).
## 함정
- README의 생성 UI·상태 분리 설명은 과거 안내다. 최신 운영은 `WORKLOG.md`를 따른다.
- 티스토리 임시저장은 블로그당 하나라 동시 편집이 서로 덮어쓴다. 편집 세션을 겹치지 않는다.
- 카테고리는 인덱스 대신 이름으로 찾고, 예약 날짜는 `YYYY-MM-DD`로 지정한다.
- 발행 성공 문구·검색 결과만 믿지 않는다. 최신 기록대로 관리 목록 첫 페이지에서 실제 글을 확인한다.
- 오래된 동일 URL 탭이 검증을 오도할 수 있다. 대상 탭을 확인하며 CAPTCHA는 사용자에게 맡긴다(아래 CHACAP 으로 폰에 중계).
- 첨부는 툴바 ‘첨부 → 사진’ 경로를 사용한다. 상세 재현·미해결 사항은 WORKLOG 참조.
## CHACAP — 캡챠 텔레그램 중계 (2026-11-17)
- 캡챠 화면을 대표님 텔레그램 봇으로 보내고, **대표님 답장 글자를 그대로** 입력칸에 넣는다. 스스로 풀지 않는다(답 추측 코드 추가 금지).
- 명령: `scripts/chacap.sh setup`(봇·채팅 연결) · `ping`(폰 왕복 시험) · `selftest`(텔레그램 없이 Aside 쪽 시험) · `relay --tid <id>|--match <정규식>`.
- 비밀: 봇 토큰은 키체인 서비스 `chacap-telegram` 계정 `bot`(대표님이 직접 넣음), 대표님 채팅 id 는 같은 서비스 계정 `chat`(setup 이 넣음). 값은 어디에도 적지 않는다.
- 토큰 넣는 법(대표님): `security add-generic-password -U -s chacap-telegram -a bot -w` → 프롬프트에 붙여넣기(셸 기록에 안 남음).
- 발행 스크립트가 알아서 부른다(`publish_waiting.py`, `cedar_post.sh`). 봇이 없으면 예전처럼 rc 7·탭 열어 둠.
## 맛집 후기 (2026-11-20 대표님)
- 예약 작업 `matjip-review`(매일 20시): 폰 사진(맥 사진 보관함, iCloud) → 새 식당 방문 찾기 → **대표님 텔레그램으로 질문** → 답장으로 받은 답 + 사진 + 카카오맵 확인 정보로 글 → **윤문(humanize) 필수** → 「맛집」 카테고리 공개 발행 → 사본 삭제.
- 도구: `scripts/matjip.sh`(scan·ask·collect·export·posted·skip, 사용법은 matjip.py 머리말) · `scripts/matjip_post.sh <글.json>`(사진 여러 장 발행, 종료코드는 publish_waiting 과 같음).
- **데이터는 레포 밖 `~/.local/share/oddo-matjip/`** — 이 레포는 공개라 사진·좌표·대표님 답·원고를 절대 넣지 않는다. 사진은 export 때 위치 등 메타데이터를 지운 JPEG 로만 올린다.
- 텔레그램 봇은 CHACAP 과 같이 쓴다 → 누가 getUpdates 로 받든 공용 일지 `~/.local/share/oddo-tg/inbox.jsonl`(`scripts/tg_inbox.py`)에 먼저 적는다. 맛집 질문은 「🍽」로 시작하고, CHACAP 은 그 질문에 단 답장을 캡챠 답으로 쓰지 않는다.
- 사진 앱이 꺼져 있으면 보관함이 iCloud 와 안 맞춰진다 → `scan` 이 뒤에서 열고 동기화를 기다린 뒤 닫는다. 새 사진은 원본이 맥에 없다(최적화 저장) → `export` 가 사진 앱 AppleScript `export … with using originals` 로 받는다.
- 하루 새 글 한도(약 5편): 괴담이 홀수 날 15시에 4편 예약 → 맛집은 홀수 날 1편·짝수 날 3편까지.
## 탭 뒷정리 (2026-11-20 대표님)
- 작업이 끝나면 **그 작업이 띄운 Aside 탭은 닫는다** — 루틴도 마찬가지(「안 그러면 어사이드 탭 계속 쌓여서 터질 거」). 발행 스크립트·`matjip.sh near` 는 스스로 닫고(캡챠 실패여도 닫음 — 늦게 풀어도 저장 안 되는 게 실측, 다음 회차가 새로 한다), mcp repl 로 연 탭은 `closeTab`. 남의 탭은 손대지 않는다.
## 여시 주간 연재 (2026-11-21 대표님)
- 예약 작업 `yeosi-weekly-serial`(매주 월 12:30): `scripts/yeosi_weekly.sh` 한 줄 — 다음 편 고르기(`yeosi_next.py`: 시리즈가 처음 올라온 순서, 같은 편은 가장 나중 글=리마스터판) → 카페 로그인 확인(풀렸으면 카카오 간편로그인 계정 클릭, 비밀번호 칸이면 멈춤) → 이미 올린 제목이면 기록만 → `cafe_promo.sh <글번호>` → 게시판 목록으로 확인 → 탭 닫기.
- 자동화 버튼 「03 다음카페 괴담 홍보」는 이 루틴으로 바뀌며 삭제됐다. 올린 기록은 레포 밖 `~/.local/share/oddo-yeosi/posted.json`.
- 로그인 판정은 화면 맨 위 줄의 「로그인/로그아웃」 글자로 한다 — 게시판 HTML 소스엔 로그아웃 상태에도 「로그아웃」 문자열이 있다.
