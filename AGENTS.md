# Tistory_cloud
## 무엇
- 티스토리 괴담 원고 생성·연재 도구와 콘텐츠 지표를 모으는 Streamlit 파이프라인 HQ.
- 2026-09-05부터 HQ는 읽기 전용이다. 발행·시간표 편집·괴담 생성 UI를 되살리지 않는다.
## 핵심 명령
- 로컬 HQ: `streamlit run streamlit_app.py`.
- 연재 HTML 생성: `bash scripts/cedar.sh build <입력.txt>`.
- 괴담 생성 래퍼: `bash scripts/gwidam.sh two_sentence` 또는 `bash scripts/gwidam.sh nosleep`.
- 배포: Streamlit Cloud에서 저장소 `main`의 `streamlit_app.py` 선택. 별도 빌드·deploy.sh 없음.
## 구조·진입점
- `streamlit_app.py`: HQ 화면, `dashboard.py`: 지표 함수, `github_state.py`·`state/`: 공유 상태.
- `scripts/`: 생성·연재 도구, `src/`: 생성 로직, `cedar/`: 연재 자료, `output/`: 생성물.
- 인증 정보는 Streamlit Secrets·로컬 비밀 파일로 관리한다. 값은 기록하지 않는다.
## 함정
- README의 생성 UI·상태 분리 설명은 과거 안내다. 최신 운영은 `WORKLOG.md`를 따른다.
- 티스토리 임시저장은 블로그당 하나라 동시 편집이 서로 덮어쓴다. 편집 세션을 겹치지 않는다.
- 카테고리는 인덱스 대신 이름으로 찾고, 예약 날짜는 `YYYY-MM-DD`로 지정한다.
- 발행 성공 문구·검색 결과만 믿지 않는다. 최신 기록대로 관리 목록 첫 페이지에서 실제 글을 확인한다.
- 오래된 동일 URL 탭이 검증을 오도할 수 있다. 대상 탭을 확인하며 CAPTCHA는 사용자에게 맡긴다.
- 첨부는 툴바 ‘첨부 → 사진’ 경로를 사용한다. 상세 재현·미해결 사항은 WORKLOG 참조.
