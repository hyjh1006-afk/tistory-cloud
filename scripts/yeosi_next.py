#!/usr/bin/env python3
"""여시(다음카페 여성시대 「홍콩할매의 속삭임」) 주간 연재 — 다음에 올릴 티스토리 글을 고른다.

2026-11-21 대표님: "자동화 버튼은 삭제하고 너가 루틴으로 매주 월요일마다 여시에 글 올리게 해줘 시리즈 한편씩 연재 시작하면 될거같아
(티스토리에 올린 글을 복사해서 올리는거지) … 리마스터 올라와잇는건 리마스터 버전으로 연재하고 … 연재 제일 오래된게 시더빌인가 그럼 그거부터"

순서: 「레딧 시리즈 번역/…」 분류를 시리즈가 처음 올라온 순서(가장 작은 글번호)대로, 시리즈 안에서는 편 번호(N 또는 N-M)순.
같은 편이 여러 번 올라와 있으면 가장 나중 글(=리마스터판)만 쓴다. 이미 올린 글은 state 에 적어 두고 다시 안 올린다.

사용: yeosi_next.py           → "NEXT\t<글번호>\t<제목>" (없으면 "DONE")
      yeosi_next.py --done N  → N 을 올린 것으로 기록
      yeosi_next.py --list    → 남은 순서 전체
데이터: ~/.local/share/oddo-yeosi/posted.json (첫 실행 때 이미 카페에 있던 시더빌 리마스터 1~3화(159·154·160)로 시작)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "state" / "post_titles.tsv"
STATE = Path.home() / ".local/share/oddo-yeosi/posted.json"
SEED = [159, 154, 160]   # 2026-11-21 여시 게시판 검색으로 확인: 시더빌 리마스터 1화 9/6 · 2화 9/9 · 3화 10/1 이미 올라가 있음


def refresh_titles() -> None:
    # 카페 홍보 목록 스크립트가 sitemap 으로 새 글 제목·분류를 캐시에 채운다(stdout 은 버림)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "cafe_promo_list.py")], capture_output=True, timeout=300)


def ep_key(title: str):
    t = re.sub(r"^\[[^\]]*\]\s*", "", title)
    m = re.search(r"(\d+)(?:-(\d+))?\s*[.\s(]", t + " ")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 0)


def queue() -> list[tuple[int, str]]:
    rows = []
    for line in CACHE.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[1].startswith("레딧 시리즈 번역/") and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1].split("/", 1)[1], parts[2]))
    series: dict[str, list] = {}
    for pid, s, t in rows:
        series.setdefault(s, []).append((pid, t))
    out = []
    for s in sorted(series, key=lambda k: min(p for p, _ in series[k])):
        # 같은 편(번호)이 여러 번 올라와 있으면 가장 나중 글 = 리마스터판을 쓴다.
        # (왼쪽/오른쪽 게임은 1-1~1-3 에만 「(리마스터)」가 붙고 178~215 는 표시 없이 다시 올린 판이라 「표시」로 고르면 빠진다 — 11/21 실측)
        best: dict = {}
        for pid, t in series[s]:
            k = ep_key(t)
            if k == (9999, 0):
                k = (9999, pid)          # 번호를 못 읽은 글은 각자 따로
            if k not in best or pid > best[k][0] or ("리마스터" in t and "리마스터" not in best[k][1]):
                best[k] = (pid, t)
        out += [best[k] for k in sorted(best)]
    return out


def load() -> list[int]:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))["posted"]
    return list(SEED)


def save(posted: list[int]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"posted": posted}, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    if "--done" in sys.argv:
        pid = int(sys.argv[sys.argv.index("--done") + 1])
        posted = load()
        if pid not in posted:
            posted.append(pid)
        save(posted)
        print(f"DONE-MARKED\t{pid}")
        return 0
    refresh_titles()
    posted = set(load())
    q = [(p, t) for p, t in queue() if p not in posted]
    if "--list" in sys.argv:
        for p, t in q:
            print(f"{p}\t{t}")
        return 0
    if not q:
        print("DONE")
        return 0
    print(f"NEXT\t{q[0][0]}\t{q[0][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
