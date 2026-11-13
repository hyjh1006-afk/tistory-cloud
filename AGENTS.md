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
- 오래된 동일 URL 탭이 검증을 오도할 수 있다. 대상 탭을 확인하며 CAPTCHA는 사용자에게 맡긴다.
- 첨부는 툴바 ‘첨부 → 사진’ 경로를 사용한다. 상세 재현·미해결 사항은 WORKLOG 참조.
