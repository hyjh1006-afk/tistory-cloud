#!/usr/bin/env python3
"""카페 홍보 버튼용 — 블로그 공개 글 '전체' 목록을 만든다.

RSS 는 최근 10편만 준다(블로그 설정). 그래서 sitemap.xml 로 공개 글 전체 id 를 얻고,
제목·분류는 글마다 한 번만 받아 state/post_titles.tsv 에 캐시한다(다음 실행은 새 글만 받음).

stdout: "<id> | <제목>"  (Life/ 분류 제외, id 내림차순)
stderr: 진행 상황
"""
import html
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BLOG = "https://tester188.tistory.com"
CACHE = Path(__file__).resolve().parent.parent / "state" / "post_titles.tsv"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

RE_TITLE = re.compile(r'og:title"\s+content="([^"]*)"')
RE_CAT = re.compile(r'class="category">([^<]*)<')


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def public_ids():
    sm = get(f"{BLOG}/sitemap.xml")
    ids = {int(m) for m in re.findall(rf"<loc>{re.escape(BLOG)}/(\d+)</loc>", sm)}
    return ids


def load_cache():
    out = {}
    if CACHE.exists():
        for line in CACHE.read_text("utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].isdigit():
                out[int(parts[0])] = (parts[1], parts[2])
    return out


def save_cache(cache):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        "".join(f"{i}\t{cache[i][0]}\t{cache[i][1]}\n" for i in sorted(cache)),
        "utf-8",
    )


def fetch_one(pid):
    try:
        h = get(f"{BLOG}/{pid}")
    except Exception as e:  # 비공개(403)·삭제(404)·일시 오류 — 캐시하지 않고 다음에 재시도
        return pid, None, str(e)
    t = RE_TITLE.search(h)
    c = RE_CAT.search(h)
    if not t:
        return pid, None, "제목 없음"
    title = html.unescape(t.group(1)).strip().replace("\t", " ")
    cat = html.unescape(c.group(1)).strip() if c else ""
    return pid, (cat, title), None


def main():
    try:
        ids = public_ids()
    except Exception as e:
        print(f"사이트맵을 못 읽었습니다: {e}", file=sys.stderr)
        return 1
    if not ids:
        print("사이트맵에 글이 없습니다", file=sys.stderr)
        return 1

    cache = load_cache()
    todo = sorted(ids - set(cache), reverse=True)
    if todo:
        print(f"새 글 {len(todo)}편의 제목을 받는 중… (처음 한 번만 오래 걸립니다)", file=sys.stderr)
        done = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            for pid, val, err in ex.map(fetch_one, todo):
                done += 1
                if val:
                    cache[pid] = val
                else:
                    print(f"  · {pid} 건너뜀 ({err})", file=sys.stderr)
                if done % 20 == 0:
                    print(f"  {done}/{len(todo)}", file=sys.stderr)
        save_cache(cache)
        print(f"목록 갱신 완료 — 공개 글 {len(ids)}편", file=sys.stderr)

    rows = []
    for pid in sorted(ids, reverse=True):
        got = cache.get(pid)
        if not got:
            continue
        cat, title = got
        if cat.startswith("Life/"):
            continue
        rows.append(f"{pid} | {title}")
    if not rows:
        print("올릴 수 있는 글이 없습니다", file=sys.stderr)
        return 1
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
