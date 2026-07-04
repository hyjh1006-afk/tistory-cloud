# 👻 괴담 글 생성기 — 클라우드 버전

폰에서 어디서나 접속해서 버튼 한 번으로 티스토리용 괴담 글(HTML)을 만드는 웹앱입니다.
Reddit 수집 → Gemini 번역 → HTML 생성까지 서버가 알아서 하고, 번호/사용 기록은 이 저장소의 `state/` 폴더에 자동 보존됩니다.

## 처음 한 번만 하면 되는 배포 (약 10분)

### 1. GitHub에 이 폴더 올리기
1. https://github.com 로그인 → 우측 상단 `+` → **New repository**
2. 이름: `tistory-cloud` (아무거나 OK), **Private** 선택 → Create
3. PC에서 이 폴더를 push (아래 명령은 Claude/터미널이 대신 해줄 수 있음)

### 2. GitHub 토큰 만들기 (상태 저장용)
1. GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens** → Generate new token
2. Repository access: **Only select repositories** → `tistory-cloud` 선택
3. Permissions → Repository permissions → **Contents: Read and write**
4. Generate → 토큰 복사 (한 번만 보여줌!)

### 3. Streamlit Cloud에 배포
1. https://share.streamlit.io → **Sign in with GitHub**
2. **Create app** → Deploy a public app from GitHub → 저장소 `tistory-cloud`, 브랜치 `main`, 파일 `streamlit_app.py`
3. **Advanced settings → Secrets**에 `DEPLOY_SECRETS.txt` 내용 붙여넣기 (GITHUB_TOKEN 자리에 2번 토큰)
4. Deploy → 1~2분 뒤 앱 주소 생성 (예: `https://xxxx.streamlit.app`)

### 4. 아이폰에서 앱처럼 쓰기
Safari로 앱 주소 열기 → 공유 버튼 → **홈 화면에 추가** → 끝!

## 사용법
1. 홈 화면 아이콘 탭
2. 모드 선택 → **⚡ 글 생성**
3. 완성된 HTML 복사 → 티스토리 앱 글쓰기(HTML 모드) 붙여넣기 → 예약

## 주의
- 무료 서버라 오래 안 쓰면 잠들어요. 첫 접속 시 "깨우는 중" 화면이 나오면 30초쯤 기다리면 됩니다.
- **집 PC 프로그램과 번호/사용 기록이 따로 갑니다.** 클라우드로 옮긴 뒤에는 클라우드만 쓰는 걸 권장.
- 수집 10분 간격 제한 있음 (Reddit 차단 방지).

## secrets 형식 (Streamlit Cloud → App settings → Secrets)
```toml
GEMINI_API_KEY = "제미나이 키"
GITHUB_TOKEN = "github_pat_..."
STATE_REPO = "본인아이디/tistory-cloud"
STATE_BRANCH = "main"
```
