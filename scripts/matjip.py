# -*- coding: utf-8 -*-
"""맛집 후기 도우미 — 폰 사진(맥 사진 보관함, iCloud 동기화)에서 새 식당 방문을 찾고, 대표님께 텔레그램으로 묻고, 답을 모은다.

2026-11-20 대표님:
  "앞으로도 내가 폰으로 음식이랑 식당 사진같은거 추가해두면 너가 주기적으로 한번씩 보고 맛집 후기 글 올리도록 세팅"
  "사진에 보이는거랑 식당 정보만 쓰면 … 재미가 없으니까 … 나에게 질문할 것들을 텔레그램으로 질문하도록 세팅해"
  "이번주거부터만 시작하자" → 첫 기준점 2026-11-16 00:00 (KST, 사진이 보관함에 들어온 시각 기준)

⚠️ 이 레포는 공개다. 사진·좌표·대표님 답은 전부 레포 밖 DATA 폴더에만 둔다(아래). 커밋 금지.

사용: scripts/matjip.sh <명령>
  scan                   사진 앱을 깨워 동기화 → 기준점 뒤로 들어온 카메라 사진을 방문 단위로 묶는다(토큰 0).
                         새 방문마다 DATA/visits/<id>/sheet.jpg(밀착 인화) 와 visit.json 을 만든다.
  status                 방문 목록과 상태(new·asked·answered·posted·skip)
  skip <id> [이유]       음식·식당 방문이 아니면 건너뜀 표시
  ask <id> <질문파일>    고른 사진 몇 장 + 질문을 대표님 텔레그램으로. 질문 메시지에 「답장」으로 답하시게 안내.
                         --photos 1,4,7 (sheet 번호, 기본 앞에서 4장)
  collect [--wait 분]    텔레그램 답을 모은다(답장 연결 → 해당 방문, 아니면 질문 뒤 온 일반 메시지). 받아 둔 답은 visit.json 에.
                         --wait 이면 첫 답이 올 때까지 기다리고, 답이 오면 2분 더 조용할 때까지 이어 받는다.
  export <id> <번호...>  고른 사진의 원본을 사진 앱에서 받아 1400px JPEG 로 줄이고 위치 등 메타데이터를 지운다 → DATA/visits/<id>/img/
  near <id> [키워드...]  사진 위치를 지도 가운데 두고 카카오맵 검색(기본 「음식점」) — 가게 이름을 위치로 찾는다(대표님 11/20 「식당 이름은 사진 위치 보고 파악해서」)
  map <id> --label 이름  그 위치의 작은 지도 그림(OpenStreetMap, 출처 표기) → img/<id>_map.jpg
  clip <id>              그 방문 시간·위치의 영상을 찾아 원본을 받고, 영상마다 장면 6컷 확인판(vids/v<n>_sheet.jpg)을 만든다
  clip <id> <n> [--start 초] [--len 초]
                         n번 영상을 소리 없는 반복 움짤(GIF, 폭 480, 최대 6초)로 → img/<id>_v<n>.gif — 본문에 사진처럼 넣는다
                         (대표님 11/22 「거기서 찍은 영상도 있으면 같이 올리려면」)
  posted <id> <주소>     올린 뒤 표시 + 사진 원본·내보낸 사본 삭제(대표님 11/13 「업로드 끝나면 용량 정리, 백업 없이」)
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tg_inbox  # noqa: E402

LIB = Path.home() / "Pictures/Photos Library.photoslibrary"
DB = LIB / "database/Photos.sqlite"
PSI = LIB / "database/search/psi.sqlite"
DATA = Path.home() / ".local/share/oddo-matjip"
STATE = DATA / "state.json"
START = "2026-11-16 00:00"          # 「이번주거부터」
APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
KST = dt.timezone(dt.timedelta(hours=9))
GAP_MIN = 90                        # 이만큼 사진이 끊기면 다른 방문
GAP_M = 400                         # 이만큼 떨어져도 다른 방문
Q_MARK = "🍽"                        # 질문 메시지 머리 — CHACAP 은 이 메시지에 단 답장을 캡챠 답으로 쓰지 않는다


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


def apple(ts: float) -> dt.datetime:
    return (APPLE_EPOCH + dt.timedelta(seconds=ts)).astimezone(KST)


def to_apple(s: str) -> float:
    return (dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST) - APPLE_EPOCH).total_seconds()


def load_state() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"checkpoint": START, "visits": {}}


def save_state(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def vdir(vid: str) -> Path:
    return DATA / "visits" / vid


def dist_m(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


# ── 사진 보관함 ──────────────────────────────────────────────────────────
def photos_running() -> bool:
    return subprocess.run(["pgrep", "-x", "Photos"], capture_output=True).returncode == 0


def sync_photos(max_wait: int = 180) -> bool:
    """사진 앱이 꺼져 있으면 보관함이 iCloud 와 안 맞춰진다(2026-11-20 실측: 앱이 꺼진 채 5일치가 안 들어와 있었음).
    뒤에서 열고, 들어온 장수가 1분 동안 안 바뀌면 끝. 우리가 연 거면 True(나중에 닫는다)."""
    opened = not photos_running()
    if opened:
        subprocess.run(["open", "-g", "-a", "Photos"], capture_output=True)
    last, stable_since, t0 = None, time.time(), time.time()
    while time.time() - t0 < max_wait:
        time.sleep(15)
        try:
            c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute("select count(*), max(ZADDEDDATE) from ZASSET").fetchone()
        except sqlite3.Error:
            continue
        if c != last:
            last, stable_since = c, time.time()
        elif time.time() - stable_since >= 60 and time.time() - t0 >= 75:
            break
    return opened


def warn_if_phone_not_uploading(days: float = 2.0) -> None:
    """맥 보관함의 가장 최근 사진이 며칠째 그대로면 폰 → iCloud 업로드가 멈춘 것(11/23 실측: 맥 동기화는 정상, 받을 게 0).
    맥에선 못 고친다 — 대표님 텔레그램으로 폰에서 확인할 곳을 알린다(tg-alert 가 같은 문구 6시간 1회로 거른다)."""
    try:
        newest = sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute(
            "select max(ZADDEDDATE) from ZASSET where ZTRASHEDSTATE=0").fetchone()[0]
    except sqlite3.Error:
        return
    if newest is None:
        return
    age_d = (time.time() - (newest + 978307200)) / 86400
    if age_d < days:
        return
    since = time.strftime("%m/%d %H:%M", time.localtime(newest + 978307200))
    print(f"WARN\t폰 사진이 {since} 뒤로 맥에 안 들어옴({age_d:.0f}일) — 폰의 iCloud 사진 업로드 확인 필요")
    msg = (f"📷 [맛집 후기] 폰 사진이 {since} 뒤로 iCloud 에 안 올라와요(맥은 정상 동기화). "
           "폰 사진 앱 → 보관함 맨 아래 상태(일시 정지·저전력·저장 공간)를 보고 「재개」, "
           "LTE 에서도 올리려면 설정 → 사진 → 셀룰러 데이터 켜기.")
    subprocess.run([str(Path.home() / ".claude/tools/tg-alert.sh"), msg], capture_output=True, timeout=60)


def quit_photos() -> None:
    subprocess.run(["osascript", "-e", 'tell application "Photos" to quit'], capture_output=True, timeout=30)


def derivative(u: str) -> str | None:
    fs = sorted(glob.glob(str(LIB / "resources/derivatives" / u[0] / f"{u}_1_*.jpeg"))) \
        + sorted(glob.glob(str(LIB / "resources/derivatives" / u[0] / f"{u}_*.jpeg"))) \
        + sorted(glob.glob(str(LIB / "resources/derivatives/masters" / u[0] / f"{u}_*.jpeg")))
    return fs[0] if fs else None


VID_PAD_MIN = 15                    # 방문 사진 앞뒤 이만큼 안에 찍힌 영상까지 그 방문 것으로 본다


def find_videos(con, v: dict) -> list[dict]:
    """방문(첫 사진~끝 사진 ± VID_PAD_MIN, 방문 좌표 GAP_M 안)에 찍힌 영상. 위치 없는 영상은 어디 건지 몰라 뺀다."""
    t0 = dt.datetime.fromisoformat(v["t0"]).timestamp() - APPLE_EPOCH.timestamp() - VID_PAD_MIN * 60
    t1 = dt.datetime.fromisoformat(v["t1"]).timestamp() - APPLE_EPOCH.timestamp() + VID_PAD_MIN * 60
    out = []
    for u, cr, dur, la, lo in con.execute(
            "select ZUUID, ZDATECREATED, ZDURATION, ZLATITUDE, ZLONGITUDE from ZASSET where ZTRASHEDSTATE=0 and ZHIDDEN=0 and ZKIND=1 "
            "and ZDATECREATED >= ? and ZDATECREATED < ? order by ZDATECREATED", (t0, t1)):
        if la is None or la < -90 or dist_m((la, lo), (v["lat"], v["lon"])) > GAP_M:
            continue
        out.append({"uuid": u, "t": apple(cr).strftime("%H:%M:%S"), "dur": round(dur or 0, 1)})
    return out


def psi_tags(uuids: list[str]) -> dict[str, dict]:
    """사진 앱 검색 색인에서 장소 이름(1700)·장소 분류(1701)·도로명(2)·동(6)·시(5). 새 사진은 색인이 늦을 수 있다."""
    import struct
    out: dict[str, dict] = {}
    try:
        s = sqlite3.connect(f"file:{PSI}?mode=ro", uri=True)
        want = set(uuids)
        ids = {}
        for rid, a, b in s.execute("select rowid, uuid_0, uuid_1 from assets"):
            u = str(uuid.UUID(bytes=struct.pack("<q", a) + struct.pack("<q", b))).upper()
            if u in want:
                ids[rid] = u
        if not ids:
            return out
        q = f"select ga.assetid, g.category, g.content_string from ga join groups g on g.rowid = ga.groupid where ga.assetid in ({','.join(map(str, ids))}) and g.category in (1700,1701,2,5,6,1500)"
        for rid, cat, txt in s.execute(q):
            d = out.setdefault(ids[rid], {})
            d.setdefault(str(cat), [])
            t = (txt or "").strip("\x00")
            if t and t not in d[str(cat)]:
                d[str(cat)].append(t)
    except sqlite3.Error:
        pass
    return out


def cmd_scan(a) -> int:
    st = load_state()
    opened = sync_photos() if not a.no_sync else False
    if not a.no_sync:
        warn_if_phone_not_uploading()
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        q = ("select ZUUID, ZDATECREATED, ZADDEDDATE, ZLATITUDE, ZLONGITUDE, ZFILENAME, ZKINDSUBTYPE from ZASSET "
             "where ZTRASHEDSTATE=0 and ZHIDDEN=0 and ZKIND=0 and ")
        if a.date:
            # 대표님이 날짜를 집어 주신 옛 방문 — 찍은 날짜로 고르고 체크포인트는 건드리지 않는다
            conds = " or ".join("(ZDATECREATED >= ? and ZDATECREATED < ?)" for _ in a.date)
            args = [x for d in a.date for x in (to_apple(d + " 00:00"), to_apple(d + " 00:00") + 86400)]
            rows = con.execute(q + f"({conds}) order by ZDATECREATED", args).fetchall()
        else:
            rows = con.execute(q + "ZADDEDDATE > ? order by ZDATECREATED", (to_apple(st["checkpoint"]),)).fetchall()
    finally:
        if opened:
            quit_photos()
    known = {u for v in st["visits"].values() for u in v["uuids"]}
    cams, max_added = [], None
    for u, cr, ad, la, lo, fn, sub in rows:
        max_added = max(max_added or ad, ad)
        if u in known or sub == 10 or str(fn).lower().endswith(".png"):   # 스크린샷·PNG(저장 이미지) 제외
            continue
        if la is None or la < -90:                                         # 위치 없는 사진(받은 사진 등) 제외
            continue
        cams.append({"uuid": u, "t": apple(cr), "lat": la, "lon": lo})
    groups: list[list[dict]] = []
    for c in cams:
        g = groups[-1] if groups else None
        if g and (c["t"] - g[-1]["t"]).total_seconds() <= GAP_MIN * 60 and dist_m((c["lat"], c["lon"]), (g[0]["lat"], g[0]["lon"])) <= GAP_M:
            g.append(c)
        else:
            groups.append([c])
    new = []
    for g in groups:
        # 동기화가 덜 된 채 지난 scan 이 만든 방문(아직 안 물어본 것)과 붙어 있으면 거기에 합친다
        host = None
        for v in st["visits"].values():
            if v["status"] != "new" or "t0" not in v:
                continue
            t0, t1 = dt.datetime.fromisoformat(v["t0"]), dt.datetime.fromisoformat(v["t1"])
            near_t = (g[0]["t"] - t1).total_seconds() <= GAP_MIN * 60 and (t0 - g[-1]["t"]).total_seconds() <= GAP_MIN * 60
            if near_t and dist_m((g[0]["lat"], g[0]["lon"]), (v["lat"], v["lon"])) <= GAP_M:
                host = v
                break
        if host:
            old = [{"uuid": u, "t": dt.datetime.fromisoformat(host["t0"]), "lat": host["lat"], "lon": host["lon"]} for u in host["uuids"]]
            g = sorted(old + g, key=lambda x: x["t"])
            del st["visits"][host["id"]]
        vid = host["id"] if host else g[0]["t"].strftime("%Y%m%d-%H%M")
        while vid in st["visits"]:
            vid += "b"
        tags = psi_tags([x["uuid"] for x in g])
        agg: dict[str, list] = {}
        for t in tags.values():
            for k, vals in t.items():
                for v in vals:
                    agg.setdefault(k, [])
                    if v not in agg[k]:
                        agg[k].append(v)
        d = vdir(vid)
        d.mkdir(parents=True, exist_ok=True)
        sheet = make_sheet([x["uuid"] for x in g], d / "sheet.jpg")
        lat = sum(x["lat"] for x in g) / len(g)
        lon = sum(x["lon"] for x in g) / len(g)
        v = {"id": vid, "status": "new", "from": g[0]["t"].strftime("%Y-%m-%d %H:%M"), "to": g[-1]["t"].strftime("%H:%M"),
             "t0": g[0]["t"].isoformat(), "t1": g[-1]["t"].isoformat(),
             "lat": round(lat, 6), "lon": round(lon, 6), "uuids": [x["uuid"] for x in g],
             "place_hint": agg.get("1700", []), "place_kind": agg.get("1701", []),
             "addr_hint": " ".join((agg.get("5", [])[:1] + agg.get("6", [])[:1] + agg.get("2", [])[:1])),
             "scenes": agg.get("1500", [])[:8], "sheet": str(sheet) if sheet else None}
        v["videos"] = find_videos(con, v)
        st["visits"][vid] = v
        new = [x for x in new if x["id"] != vid] + [v]
    if max_added is not None and not a.date:
        st["checkpoint"] = max(st["checkpoint"], apple(max_added).strftime("%Y-%m-%d %H:%M"))
    save_state(st)
    pending = [v for v in st["visits"].values() if v["status"] in ("new", "asked", "answered")]
    print(f"NEW={len(new)} PENDING={len(pending)} CHECKPOINT={st['checkpoint']}")
    for v in pending:
        print(f"VISIT\t{v['id']}\t{v['status']}\t{v['from']}~{v['to']}\t{len(v['uuids'])}장\t"
              f"장소힌트={','.join(v['place_hint'][:3]) or '-'}\t분류={','.join(v['place_kind'][:3]) or '-'}\t"
              f"주소={v['addr_hint'] or '-'}\t좌표={v['lat']},{v['lon']}\t장면={','.join(v['scenes'][:5])}\t영상={len(v.get('videos', []))}개\tSHEET={v['sheet']}")
    return 0


def make_sheet(uuids: list[str], out: Path) -> Path | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    ims = []
    for i, u in enumerate(uuids[:30]):
        f = derivative(u)
        if not f:
            continue
        im = Image.open(f).convert("RGB")
        im.thumbnail((260, 260))
        ims.append((i + 1, im))
    if not ims:
        return None
    cols = min(6, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new("RGB", (cols * 264, rows * 264), "white")
    for k, (n, im) in enumerate(ims):
        x, y = (k % cols) * 264 + 2, (k // cols) * 264 + 2
        sh.paste(im, (x, y))
        ImageDraw.Draw(sh).rectangle([x, y, x + 30, y + 22], fill="black")
        ImageDraw.Draw(sh).text((x + 6, y + 5), str(n), fill="white")
    sh.save(out, quality=82)
    return out


# ── 텔레그램 ─────────────────────────────────────────────────────────────
def cmd_ask(a) -> int:
    st = load_state()
    v = st["visits"][a.id]
    q = Path(a.questions).read_text(encoding="utf-8").strip()
    picks = [int(x) for x in a.photos.split(",")] if a.photos else list(range(1, min(4, len(v["uuids"])) + 1))
    files = [derivative(v["uuids"][n - 1]) for n in picks if 0 < n <= len(v["uuids"])]
    files = [f for f in files if f]
    tg = tg_inbox.Tg()
    if files:
        tg.media_group([strip_to_jpeg_bytes(f, 1024) for f in files])
    head = f"{Q_MARK} 맛집 후기 질문 · {v['from']}\n(이 메시지를 길게 눌러 「답장」으로 편하게 써 주세요. 여러 번 나눠 보내셔도 돼요)\n\n"
    m = tg.send(head + q)
    v.setdefault("asks", []).append({"msg_id": m["message_id"], "at": now_kst().strftime("%Y-%m-%d %H:%M:%S"), "date": m["date"]})
    v["status"] = "asked"
    save_state(st)
    print(f"ASKED {a.id} msg_id={m['message_id']} 사진 {len(files)}장")
    return 0


def match_answers(st: dict, msgs: list[dict]) -> dict[str, list[dict]]:
    asked = [v for v in st["visits"].values() if v["status"] in ("asked", "answered") and v.get("asks")]
    by_msg = {a["msg_id"]: v["id"] for v in asked for a in v["asks"]}
    got: dict[str, list[dict]] = {}
    for m in msgs:
        if not m.get("text") or m.get("used_by"):
            continue
        rid = (m.get("reply_to") or {}).get("message_id")
        vid = by_msg.get(rid)
        if not vid and rid is None:
            # 답장이 아닌 일반 메시지: 그 시각 직전에 질문을 받은 방문이 하나뿐일 때만 그 방문 답으로 본다
            cands = [v for v in asked if any(a["date"] <= m["date"] for a in v["asks"])]
            cands.sort(key=lambda v: max(a["date"] for a in v["asks"]))
            if cands and len([v for v in cands if v["status"] == "asked"]) <= 1:
                vid = cands[-1]["id"]
        if vid:
            got.setdefault(vid, []).append(m)
    return got


def cmd_collect(a) -> int:
    st = load_state()
    tg = tg_inbox.Tg()
    deadline = time.time() + a.wait * 60
    quiet_until = None
    while True:
        tg.peek()                                   # 새 메시지를 일지에 적기만 한다(확인 처리 안 함 — CHACAP 몫)
        st = load_state()                           # 기다리는 동안 scan·ask 가 state 를 바꿀 수 있다 — 매번 새로 읽는다(11/22 오래 든 state 로 덮어써 방문 하나가 사라짐)
        msgs = tg_inbox.read_journal()
        got = match_answers(st, msgs)
        changed = False
        for vid, ms in got.items():
            v = st["visits"][vid]
            seen = {x["update_id"] for x in v.get("answers", [])}
            for m in ms:
                if m["update_id"] not in seen:
                    v.setdefault("answers", []).append({"update_id": m["update_id"], "date": m["date"], "text": m["text"]})
                    changed = True
            if v.get("answers") and v["status"] == "asked":
                v["status"] = "answered"
                # 대표님 11/22 「열심히 답장보내놨는데 왜 인식안되지」 — 받았다는 걸 텔레그램으로 바로 알린다
                try:
                    tg.send(f"{Q_MARK} 답 받았어요 · {v['from']} — 이걸로 후기 쓸게요 ✍️")
                except Exception:
                    pass
        if changed:
            save_state(st)
            quiet_until = time.time() + 120
        if a.wait <= 0 or (quiet_until and time.time() > quiet_until) or time.time() > deadline:
            break
        time.sleep(10)
    for v in st["visits"].values():
        if v["status"] in ("asked", "answered"):
            print(f"VISIT\t{v['id']}\t{v['status']}\t답 {len(v.get('answers', []))}개")
            for x in v.get("answers", []):
                print("  ANSWER\t" + x["text"].replace("\n", " / "))
    return 0


def strip_to_jpeg_bytes(src: str, max_px: int) -> bytes:
    from io import BytesIO
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.thumbnail((max_px, max_px))
    b = BytesIO()
    im.save(b, "JPEG", quality=88)          # exif 를 넘기지 않으니 위치·기기 정보가 안 따라간다
    return b.getvalue()


def cmd_export(a) -> int:
    st = load_state()
    v = st["visits"][a.id]
    out = vdir(a.id) / "img"
    raw = vdir(a.id) / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    opened = not photos_running()
    paths = []
    try:
        for n in a.nums:
            u = v["uuids"][n - 1]
            before = set(os.listdir(raw))
            r = subprocess.run(["osascript", "-e", f'tell application "Photos" to export {{media item id "{u}/L0/001"}} to POSIX file "{raw}" with using originals'],
                               capture_output=True, text=True, timeout=300)
            new = sorted(set(os.listdir(raw)) - before)
            src = str(raw / new[0]) if new else derivative(u)
            if not src:
                print(f"  ✗ {n}번 원본·미리보기 둘 다 없음 ({r.stderr.strip()[:120]})")
                continue
            if src.lower().endswith((".heic", ".heif")):
                conv = str(raw / f"conv_{n}.jpg")
                subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", conv], capture_output=True)
                src = conv
            dst = out / f"{a.id}_{n:02d}.jpg"
            dst.write_bytes(strip_to_jpeg_bytes(src, 1400))
            paths.append(str(dst))
    finally:
        shutil.rmtree(raw, ignore_errors=True)
        if opened:
            quit_photos()
    # 검사: 위치 정보가 정말 없는가
    from PIL import Image
    for p in paths:
        ex = Image.open(p).getexif()
        if ex.get(0x8825) or len(ex):
            print(f"  ✗ 메타데이터 남음: {p}")
            return 1
    v["images"] = paths
    save_state(st)
    for p in paths:
        print("IMG\t" + p)
    return 0


def export_original(u: str, dst_dir: Path) -> Path | None:
    before = set(os.listdir(dst_dir))
    subprocess.run(["osascript", "-e", f'tell application "Photos" to export {{media item id "{u}/L0/001"}} to POSIX file "{dst_dir}" with using originals'],
                   capture_output=True, text=True, timeout=600)
    new = sorted(set(os.listdir(dst_dir)) - before)
    return dst_dir / new[0] if new else None


def cmd_clip(a) -> int:
    st = load_state()
    v = st["visits"][a.id]
    vids = vdir(a.id) / "vids"
    vids.mkdir(parents=True, exist_ok=True)
    if a.n is None:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        v["videos"] = find_videos(con, v)
        save_state(st)
        if not v["videos"]:
            print("VIDEOS=0")
            return 0
        opened = not photos_running()
        try:
            for n, x in enumerate(v["videos"], 1):
                src = next(iter(sorted(vids.glob(f"v{n}.m*"))), None)
                if not src:
                    tmp = vids / f"tmp{n}"
                    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
                    got = export_original(x["uuid"], tmp)
                    if not got:
                        print(f"  ✗ {n}번 영상 원본을 못 받음")
                        continue
                    src = vids / f"v{n}{got.suffix.lower()}"
                    got.rename(src); shutil.rmtree(tmp, ignore_errors=True)
                sheet = vids / f"v{n}_sheet.jpg"
                # 장면 6컷(얼굴·사람이 나오는지, 어디를 자를지 보려고)
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf",
                                f"fps=6/{max(x['dur'], 0.5)},scale=360:-2,tile=6x1", "-frames:v", "1", str(sheet)], capture_output=True)
                print(f"VIDEO\t{n}\t{x['t']}\t{x['dur']}초\tSHEET={sheet if sheet.exists() else '-'}")
        finally:
            if opened:
                quit_photos()
        return 0
    x = v["videos"][a.n - 1]
    src = next(iter(sorted(vids.glob(f"v{a.n}.m*"))), None)
    if not src:
        print(f"  ✗ 먼저 clip {a.id} 로 원본을 받으세요")
        return 1
    length = min(a.len or x["dur"], 6.0, max(x["dur"] - a.start, 0.5))
    out = vdir(a.id) / "img"; out.mkdir(parents=True, exist_ok=True)
    gif = out / f"{a.id}_v{a.n}.gif"
    # 소리 없는 반복 GIF — 팔레트를 영상에서 뽑아 번짐을 줄이고, 10fps·폭 480 으로 크기를 누른다(11/22 대하 4.5초: 540·12fps 7.8MB → 480·10fps 5.2MB). GIF 에는 위치 정보가 안 실린다.
    vf = f"fps=10,scale={a.width}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5"
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(a.start), "-t", f"{length:.2f}", "-i", str(src),
                        "-vf", vf, "-loop", "0", str(gif)], capture_output=True, text=True)
    if r.returncode or not gif.exists():
        print(f"  ✗ 움짤 변환 실패: {r.stderr[:200]}")
        return 1
    mb = gif.stat().st_size / 1e6
    if mb > 9:
        print(f"  ✗ 움짤이 너무 큼 {mb:.1f}MB — --len 을 줄이거나 --width 를 낮추세요")
        return 1
    v.setdefault("clips", [])
    if str(gif) not in v["clips"]:
        v["clips"].append(str(gif))
    save_state(st)
    print(f"CLIP\t{gif}\t{length:.1f}초\t{mb:.1f}MB")
    return 0


# ── 가게 찾기·위치 지도 ──────────────────────────────────────────────────
NEAR_JS = r"""
const A = __ARGS__;
// 우리 탭을 새로 열고 끝에 닫는다(대표님 11/20: 띄운 탭은 닫기) — 남의 카카오맵 탭은 건드리지 않는다
const P = await openTab('https://map.kakao.com/');
const conv = await P.evaluate(async ([lat, lng]) => { const r = await fetch(`/link/map/x,${lat},${lng}`); const m = r.url.match(/urlX=([\d.]+)&urlY=([\d.]+)/); return m ? [m[1], m[2]] : null; }, [A.lat, A.lng]);
if (!conv) return {error: 'coord'};
await P.goto(`https://map.kakao.com/?urlX=${conv[0]}&urlY=${conv[1]}&urlLevel=2`);
await sleep(2500);
const out = {};
for (const q of A.kws) {
  await P.fill('#search\\.keyword\\.query', q);
  await P.press('#search\\.keyword\\.query', 'Enter');
  await sleep(2200);
  out[q] = await P.evaluate(() => [...document.querySelectorAll('#info\\.search\\.place\\.list > li')].slice(0, 8).map(li => ({
    name: li.querySelector('.link_name')?.textContent.trim(),
    cate: li.querySelector('.subcategory')?.textContent.trim(),
    addr: li.querySelector('.addr p')?.textContent.trim(),
    hours: li.querySelector('.openhour')?.textContent.replace(/\s+/g, ' ').trim(),
    url: li.querySelector('a.moreview')?.href || null })));
}
try { await closeTab(P); } catch (e) {}
return out;
"""


def cmd_near(a) -> int:
    """사진 위치(방문 좌표)를 지도 가운데 두고 카카오맵 검색 — 가까운 가게가 먼저 나온다(11/20 실측: 「음식점」 검색이 반경 수십 m 가게부터)."""
    st = load_state()
    v = st["visits"][a.id]
    kws = a.kws or ["음식점"]
    code = ("const __o = await (async () => {" + NEAR_JS.replace("__ARGS__", json.dumps({"lat": v["lat"], "lng": v["lon"], "kws": kws}, ensure_ascii=False))
            + "})().catch(e => ({error: String(e).slice(0, 300)})); console.log('RESULT=' + JSON.stringify(__o));")
    p = subprocess.run([str(Path.home() / ".local/bin/aside"), "repl", code], cwd="/tmp", capture_output=True, text=True, timeout=150)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT=")), None)
    if not line:
        print("✗ aside repl 결과 없음: " + (p.stdout + p.stderr)[-300:])
        return 2
    res = json.loads(line[7:])
    if "error" in res:
        print("✗ " + res["error"])
        return 2
    for q, items in res.items():
        print(f"== {q}")
        for it in items:
            print(f"  {it['name']} | {it['cate']} | {it['addr']} | {it.get('hours') or '-'} | {it.get('url') or '-'}")
    return 0


def cmd_map(a) -> int:
    """방문 좌표를 가운데 둔 작은 위치 지도(OpenStreetMap 타일, 출처 표기 포함) → visits/<id>/img/<id>_map.jpg"""
    from io import BytesIO
    import urllib.request
    from PIL import Image, ImageDraw
    st = load_state()
    v = st["visits"][a.id]
    lat, lon, z = round(v["lat"], 4), round(v["lon"], 4), a.zoom
    n = 2 ** z
    fx = (lon + 180) / 360 * n
    fy = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    W, H = 900, 560
    cx, cy = fx * 256, fy * 256
    x0, y0 = int(cx - W / 2), int(cy - H / 2)
    img = Image.new("RGB", (W, H), "white")
    for tx in range(x0 // 256, (x0 + W) // 256 + 1):
        for ty in range(y0 // 256, (y0 + H) // 256 + 1):
            req = urllib.request.Request(f"https://tile.openstreetmap.org/{z}/{tx}/{ty}.png",
                                         headers={"User-Agent": "ODDO-blog-staticmap/1.0 (+https://oddoapps.com)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                tile = Image.open(BytesIO(r.read())).convert("RGB")
            img.paste(tile, (tx * 256 - x0, ty * 256 - y0))
            time.sleep(0.3)
    d = ImageDraw.Draw(img)
    px, py = W // 2, H // 2
    d.ellipse([px - 15, py - 44, px + 15, py - 14], fill=(231, 76, 60), outline="white", width=3)
    d.polygon([(px - 11, py - 22), (px + 11, py - 22), (px, py)], fill=(231, 76, 60))
    d.ellipse([px - 5, py - 34, px + 5, py - 24], fill="white")
    if a.label:
        try:
            from PIL import ImageFont
            f = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 26)
        except Exception:
            f = None
        tw = d.textlength(a.label, font=f) if f else len(a.label) * 8
        d.rounded_rectangle([px - tw / 2 - 12, py - 92, px + tw / 2 + 12, py - 54], radius=10, fill="white", outline=(231, 76, 60), width=2)
        d.text((px - tw / 2, py - 88), a.label, fill=(40, 40, 40), font=f)
    att = "© OpenStreetMap contributors"
    try:
        from PIL import ImageFont
        fa = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except Exception:
        fa = None
    aw = d.textlength(att, font=fa) if fa else len(att) * 7
    d.rectangle([W - aw - 16, H - 24, W, H], fill=(255, 255, 255))
    d.text((W - aw - 8, H - 21), att, fill=(60, 60, 60), font=fa)
    out = vdir(a.id) / "img"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{a.id}_map.jpg"
    img.save(path, "JPEG", quality=88)
    print("IMG\t" + str(path))
    return 0


def cmd_status(_a) -> int:
    st = load_state()
    print(f"CHECKPOINT={st['checkpoint']}")
    for v in sorted(st["visits"].values(), key=lambda x: x["id"]):
        print(f"{v['id']}\t{v['status']}\t{v['from']}\t{len(v['uuids'])}장\t{','.join(v.get('place_hint', [])[:2])}\t{v.get('url', '')}")
    return 0


def cmd_skip(a) -> int:
    st = load_state()
    v = st["visits"][a.id]
    v["status"], v["why"] = "skip", " ".join(a.why)
    shutil.rmtree(vdir(a.id), ignore_errors=True)
    save_state(st)
    print(f"SKIP {a.id}")
    return 0


def cmd_posted(a) -> int:
    st = load_state()
    v = st["visits"][a.id]
    v["status"], v["url"] = "posted", a.url
    v.pop("images", None)
    shutil.rmtree(vdir(a.id), ignore_errors=True)       # 올렸으면 사본은 필요 없다(백업 없이)
    save_state(st)
    print(f"POSTED {a.id} {a.url}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--no-sync", action="store_true"); s.add_argument("--date", action="append", help="YYYY-MM-DD (찍은 날짜, 여러 번 가능)"); s.set_defaults(f=cmd_scan)
    s = sub.add_parser("status"); s.set_defaults(f=cmd_status)
    s = sub.add_parser("skip"); s.add_argument("id"); s.add_argument("why", nargs="*"); s.set_defaults(f=cmd_skip)
    s = sub.add_parser("ask"); s.add_argument("id"); s.add_argument("questions"); s.add_argument("--photos"); s.set_defaults(f=cmd_ask)
    s = sub.add_parser("collect"); s.add_argument("--wait", type=float, default=0); s.set_defaults(f=cmd_collect)
    s = sub.add_parser("export"); s.add_argument("id"); s.add_argument("nums", type=int, nargs="+"); s.set_defaults(f=cmd_export)
    s = sub.add_parser("posted"); s.add_argument("id"); s.add_argument("url"); s.set_defaults(f=cmd_posted)
    s = sub.add_parser("near"); s.add_argument("id"); s.add_argument("kws", nargs="*"); s.set_defaults(f=cmd_near)
    s = sub.add_parser("clip"); s.add_argument("id"); s.add_argument("n", type=int, nargs="?"); s.add_argument("--start", type=float, default=0.0)
    s.add_argument("--len", type=float); s.add_argument("--width", type=int, default=480); s.set_defaults(f=cmd_clip)
    s = sub.add_parser("map"); s.add_argument("id"); s.add_argument("--label", default=""); s.add_argument("--zoom", type=int, default=17); s.set_defaults(f=cmd_map)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
