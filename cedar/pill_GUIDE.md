# 「플로리다의 필 밀」 번역 지침 (모든 편 공통)

원작: u/IEscapedFromALab, *The Pill Mills of Florida* (r/nosleep, 2016-12 ~ 2017-01). **원작자 번역 허락 받음(2026-11-08)** — 단 본문에 「원작자에게 허락받은 번역본입니다.」 문구는 **넣지 않는다**(대표님 지시, 3줄 `#note:none`).
원문: `cedar/pill_src/<id>.md` (제목 줄·원문 주소·본문). 1편 번역 완성본 `cedar/pill1.txt` 가 **문체 기준**이다 — 먼저 읽고 똑같은 말투로.

## 출력 파일 형식 (cedar_build.py 입력)
```
1줄: [Reddit] 플로리다의 필 밀 - <편번호>. <한국어 부제>
2줄: 원문 레딧 주소 (pill_src 의 2줄 그대로)
3줄: #note:none
4줄: (빈 줄)
5줄~: 본문. 문단은 빈 줄 하나로 나눈다. 원문 구분선(____)은 「* * *」 한 줄 문단으로.
```
- 마지막 편 제목 끝에만 ` (完)` 를 붙인다.
- 원문 맨 위 「Part Two / Part Three…」 링크 목록, 끝의 「Part X 링크」 같은 내비게이션은 **빼고** 이야기만 옮긴다.
- 작가가 독자에게 하는 말(댓글 고맙다, 다음 편 언제 올린다 등)은 이야기 일부로 보고 **살린다**.
- 굵게·기울임(`*...*`, `**...**`)은 강조가 꼭 필요한 곳만 `*단어*` 로 남기고, 나머지는 평문으로.

## 문체
- 화자 「윌크스」의 **해체 반말**(~했어, ~했지, ~거야). 「~다」 체로 바뀌지 않게 끝까지 한 톤.
- 대사는 원문 인물 관계대로: 처음 보는 사이·고용 관계 초반엔 존댓말, 친해진 동료·불량배끼리는 반말. 1편 기준(데이브는 처음엔 윌크스에게 존댓말, 데비는 반말).
- 욕설·마약·폭력 묘사는 **순화하지 말고** 자연스러운 한국어 욕으로(씨발, 좆같은, 존나 등). 다만 원문보다 세게 만들지는 않는다.
- 직역투 금지. 영어 어순이 비치면 다시 쓴다. 미국 고유 지명·상표는 음역하되, 한국 독자가 모를 만한 건 짧게 풀어 준다(예: 「퍼블릭스 마트」).
- 원문에 없는 설정·해설을 덧붙이지 않는다. 번역자 주석도 넣지 않는다.

## 고유명사 표기 (반드시 이대로)
| 원문 | 표기 |
|---|---|
| Wilks (화자) | 윌크스 |
| Debbie / Deborah | 데비 / 데보라 |
| George (데비 남자친구, 조직 우두머리) | 조지 |
| Dave (빨간 머리 근육맨) | 데이브 |
| Jessica (약제실) | 제시카 |
| Aaron | 애런 · Samantha 서맨사 · Lyle 라일 · Ted 테드 · Brody 브로디 |
| Carl | 칼 · Corey Franks 코리 프랭크스 · Damon 데이먼 |
| Cynthia | 신시아 · Kyle 카일 · Stigini 스티지니 · Steve 스티브 · Marshall 마셜 |
| Grace | 그레이스 · Chris 크리스 · Alyssa 얼리사 · Janette 재닛 |
| Cliff | 클리프 · Ashley 애슐리 · Byron 바이런 |
| the well-dressed man | 잘 차려입은 남자 |
| pill mill | 필 밀 (처음 나올 때만 필요하면 「진통제를 찍어 내는 병원」 식으로 풀어도 됨) |
| pill-billies | 필빌리 |
| patient(s) (따옴표 친 비꼼) | "환자(들)" |
| junkie | 약쟁이 |
| Executive Medical Solutions | 이그제큐티브 메디컬 솔루션스 |
| American Injury Clinic | 아메리칸 인저리 클리닉 |
| Roxicodone / roxy / 30s | 록시코돈 / 록시 / 30밀리짜리 |
| Xanax / soma | 자낙스 / 소마 |
| Aryan Brotherhood | 아리안 브라더후드 |
| DEA / FBI | 마약단속국(DEA) / FBI |
| West Palm Beach | 웨스트팜비치 |
| Palm Beach (Island) | 팜비치(섬) |
| Lake Worth | 레이크워스 |
| Hobe Sound | 호브사운드 |
| City Place | 시티플레이스 |
| Clematis (Street) | 클레머티스 거리 |
| Yeehaw Junction | 이호정션 |
| Loxahatchee | 록사해치 |
| Fort Lauderdale | 포트로더데일 |
| Hialeah | 하이얼리아 |
| Okeechobee | 오키초비 |
| Miami | 마이애미 |
| Bryant Park | 브라이언트 공원 |
| Publix | 퍼블릭스 마트 |
| Seminole / Calusa | 세미놀 / 칼루사 |
| Appalachia(n) | 애팔래치아 |
목록에 없는 새 이름이 나오면 표준 외래어 표기로 정하고, **결과 보고에 「새로 정한 표기」로 적는다.**

## 편 나누기
- 한 글은 한국어 **공백 빼고 7천~1만 1천 자** 정도. 지정된 개수로 나누되, 장면이 바뀌는 구분선(____) 위치에서 자른다.
- 나눈 글의 부제는 원문 편 부제를 그대로 쓰고 편번호만 2-1, 2-2 처럼.
