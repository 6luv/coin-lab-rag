"""코인마다 그 코인 자체를 다룬 위키 문서를 수집한다 (F2004: 항상 색인해야 하는 문서).

한국어 위키백과 우선, 없으면 영어. 이미 수집한 키워드는 건너뛴다 (NF2002).
위키데이터 연결이 없는 코인은 위키백과 검색으로 자체 문서를 찾는다 (제목=코인 이름·심볼 + 암호화폐 단서, D12).

사용:
  python -m scripts.collect_item_docs            # 전체
  python -m scripts.collect_item_docs --limit 20 # 상위 20개만
  python -m scripts.collect_item_docs --coin bitcoin
"""
from __future__ import annotations

import argparse
import json

import requests

from src.config import path
from src.data_prep import docs_store, wiki


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--coin", default="")
    ap.add_argument("--no-en-fallback", action="store_true")
    ap.add_argument("--no-search", action="store_true", help="연결 정보가 없는 코인의 검색을 하지 않음")
    args = ap.parse_args()

    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    if args.coin:
        coins = [c for c in coins if c["coin_id"] == args.coin]
    if args.limit:
        coins = coins[: args.limit]

    try:
        client = wiki.make_client()
    except wiki.MissingContactError as e:
        print(e)
        return 2
    manifest = docs_store.load_manifest()
    have_item_doc = {d["coin_id"] for d in docs_store.iter_docs() if d.get("is_item_doc")}
    saved = skipped = missing = 0
    for c in coins:
        if c["coin_id"] in have_item_doc:  # 코인 자체 문서를 이미 받음
            skipped += 1
            continue
        targets = []
        if c.get("kowiki_title"):
            targets.append(("ko", c["kowiki_title"]))
        if c.get("enwiki_title") and not args.no_en_fallback:
            targets.append(("en", c["enwiki_title"]))
        if not targets:
            if args.no_search or docs_store.already_collected(manifest, c["coin_id"], "item:search"):
                missing += 1
                continue
            try:
                doc = wiki.find_item_page(client, c)
            except (RuntimeError, requests.RequestException, ValueError) as e:
                print(f"  ! {c['coin_id']}: 검색 실패, 다음 실행 때 재시도 ({type(e).__name__})")
                continue
            if doc:
                out = docs_store.save_doc(doc, c, f"item:search:{doc['source_type']}:{doc['title']}", manifest, is_item_doc=True)
                saved += 1
                have_item_doc.add(c["coin_id"])
                print(f"  + {c['coin_id']}: 검색으로 찾음 {doc['source']} '{doc['title']}' ({len(doc['text']):,}자) → {out.name}")
            else:
                missing += 1
                print(f"  - {c['coin_id']}: 위키 자체 문서 없음 (CoinGecko 설명만 사용)")
            docs_store.mark_keyword(manifest, c["coin_id"], "item:search")
            docs_store.save_manifest(manifest)
            continue
        # 한국어 우선, 한국어 문서를 받지 못했을 때만 영어 (이미 받은 문서가 있으면 건너뜀)
        for lang, title in targets:
            keyword = f"item:{lang}:{title}"
            if docs_store.already_collected(manifest, c["coin_id"], keyword):
                continue  # 이 제목은 '문서 없음'으로 기록됨 → 다음 언어 시도
            doc = wiki.fetch_page(client, title, lang)
            if not doc:
                docs_store.mark_keyword(manifest, c["coin_id"], keyword)
                missing += 1
                continue
            out = docs_store.save_doc(doc, c, keyword, manifest, is_item_doc=True)
            saved += 1
            have_item_doc.add(c["coin_id"])
            print(f"  + {c['coin_id']}: {doc['source']} '{doc['title']}' ({len(doc['text']):,}자) → {out.name}")
            break
        docs_store.save_manifest(manifest)
    print(f"완료: 저장 {saved} · 이미 수집 {skipped} · 문서 없음 {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
