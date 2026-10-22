"""CoinGecko 코인 메타데이터 + 위키데이터 매핑 수집 (F2001 준비).

사용:
  python -m scripts.collect_coins              # 상위 150개 (config coins.count)
  python -m scripts.collect_coins --count 120
  python -m scripts.collect_coins --refresh    # 24시간 안에 받은 상세도 다시 받기
  python -m scripts.collect_coins --no-fetch   # API 호출 없이 data/raw 로 coins.json 만 다시 만들기

출력:
  data/raw/coingecko_raw.json   (원본, git 제외 — CoinGecko 약관상 24시간 내 갱신)
  data/source_map.json          (코인 → 위키데이터 QID, 한/영 위키 문서, 매핑 방법, 사람 검토 결과)
  data/coins.json               (정규화된 항목 목록, 색인 입력)

중간에 실패해도 받은 만큼 저장하고, 실패한 코인은 다음 실행 때 다시 시도한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import requests

from src.config import path, settings
from src.data_prep import coingecko, items, wiki

SAVE_EVERY = 5


def _load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _dump(p, data, indent=None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def main() -> int:
    cfg = settings()["coins"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=cfg["count"])
    ap.add_argument("--refresh", action="store_true", help="저장된 상세가 있어도 다시 받는다")
    ap.add_argument("--skip-wiki", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="API 를 호출하지 않고 저장된 raw 로 coins.json 만 다시 만든다")
    args = ap.parse_args()

    raw_path, map_path, coins_path = path("coins_raw"), path("source_map"), path("coins")
    raw = _load(raw_path, {"markets": [], "details": {}, "details_at": {}})
    source_map = _load(map_path, {})
    if args.no_fetch:
        if not raw["markets"]:
            print("data/raw/coingecko_raw.json 이 없습니다. 먼저 --no-fetch 없이 실행하세요.", file=sys.stderr)
            return 1
        return _write_coins(raw, source_map, coins_path, cfg)

    cg = coingecko.make_client()
    print("CoinGecko ping:", coingecko.ping(cg))
    now = datetime.now(timezone.utc)
    raw["markets"] = coingecko.markets(cg, args.count, cfg["vs_currency"])
    raw["collected_at"] = now.isoformat(timespec="seconds")
    _dump(raw_path, raw)
    print(f"markets: {len(raw['markets'])}건")

    fetched = failed = 0
    for i, m in enumerate(raw["markets"], 1):
        cid = m["id"]
        got = raw["details_at"].get(cid)
        fresh = got and now - datetime.fromisoformat(got) < timedelta(hours=24)
        if fresh and not args.refresh:
            continue
        print(f"  [{i}/{len(raw['markets'])}] detail {cid}")
        try:
            raw["details"][cid] = coingecko.coin_detail(cg, cid)
        except (RuntimeError, requests.RequestException, ValueError) as e:
            failed += 1
            print(f"    실패, 다음 실행 때 재시도: {e}")
            continue
        raw["details_at"][cid] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fetched += 1
        if fetched % SAVE_EVERY == 0:
            _dump(raw_path, raw)
    _dump(raw_path, raw)
    print(f"상세: 새로 받음 {fetched} · 실패 {failed}")

    if not args.skip_wiki:
        try:
            wc = wiki.make_client()
        except wiki.MissingContactError as e:
            print(f"{e}\n위키 매핑을 건너뜁니다. (.env 에 CONTACT_EMAIL 을 넣고 다시 실행, 또는 --skip-wiki)")
            args.skip_wiki = True
    if not args.skip_wiki:
        mapped = 0
        for m in raw["markets"]:
            if m["id"] in source_map:  # 사람 검토 결과 보존
                continue
            try:
                source_map[m["id"]] = wiki.map_coin(wc, m["id"], m["name"])
            except (RuntimeError, requests.RequestException, ValueError) as e:
                print(f"  wiki map {m['id']} 실패, 다음 실행 때 재시도: {e}")
                continue
            mapped += 1
            f = wiki.flat(source_map[m["id"]])
            print(f"  wiki map {m['id']}: {f.get('kowiki') or '-'} / {f.get('enwiki') or '-'}")
            if mapped % SAVE_EVERY == 0:
                _dump(map_path, source_map, indent=1)
        _dump(map_path, source_map, indent=1)

    return _write_coins(raw, source_map, coins_path, cfg)


def _write_coins(raw: dict, source_map: dict, coins_path, cfg: dict) -> int:
    rows = [
        items.normalize(m, raw["details"].get(m["id"]), wiki.flat(source_map.get(m["id"])), raw["collected_at"])
        for m in raw["markets"]
    ]
    _dump(coins_path, rows, indent=1)
    ko = sum(1 for r in rows if r["kowiki_title"])
    en = sum(1 for r in rows if r["enwiki_title"])
    det = sum(1 for r in rows if r["detail_collected"])
    logo = sum(1 for r in rows if r.get("image"))
    print(f"완료: 항목 {len(rows)}건 (상세 {det} · 로고 {logo}) · 한국어 위키 {ko}건 · 영어 위키 {en}건 → {coins_path}")
    if len(rows) < cfg["min_items"]:
        print(f"경고: 항목이 {cfg['min_items']}건 미만입니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
