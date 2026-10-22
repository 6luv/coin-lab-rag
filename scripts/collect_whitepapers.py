"""F2016: 코인 백서(PDF·웹 문서)를 수집한다. 출처 URL 은 CoinGecko 상세의 links.whitepaper.

기본 대상은 아직 자체 문서(위키·백서)가 없는 코인. 먼저 collect_item_docs 로 위키 문서를 채운 뒤 실행한다.
받은 원문은 data/docs/whitepaper/ 에 저장하고 git 에 올리지 않는다 (저작권: 각 프로젝트). 색인은 index_docs.

사용:
  python -m scripts.collect_whitepapers              # 자체 문서가 없는 코인만
  python -m scripts.collect_whitepapers --all        # 위키 문서가 있는 코인도 백서 추가 (출처 결합 비교용)
  python -m scripts.collect_whitepapers --coin ethena --limit 10
  python -m scripts.collect_whitepapers --prune      # 잘못 받은 문서(GitHub 미리보기 화면 등) 정리 후 다시 받기
"""
from __future__ import annotations

import argparse
import json

import requests

from src.config import path
from src.data_prep import docs_store, whitepaper


def prune(manifest: dict) -> int:
    """저장된 백서 중 지금 규칙(파일 미리보기 화면 배제, 폴더 링크 제외)에 맞지 않는 것을 지우고 재수집 기록을 푼다."""
    removed = 0
    for f in sorted(docs_store.docs_dir("whitepaper").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not (whitepaper.looks_like_viewer(d.get("text", "")) or whitepaper.resolve_url(d.get("url", "")) is None):
            continue
        f.unlink()
        entry = manifest.get(d["coin_id"], {})
        for key in ("keywords", "page_ids", "titles"):
            value = {"keywords": f"wp:{d['url']}", "page_ids": d["doc_id"], "titles": d["title"]}[key]
            if value in entry.get(key, []):
                entry[key].remove(value)
        removed += 1
        print(f"  x {d['coin_id']}: {d['url']}")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="자체 문서가 이미 있는 코인도 백서를 받는다")
    ap.add_argument("--coin", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--prune", action="store_true", help="지금 규칙에 맞지 않는 저장 문서를 지우고 다시 받을 수 있게 기록을 지운다")
    args = ap.parse_args()

    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    if args.coin:
        coins = [c for c in coins if c["coin_id"] == args.coin]
    manifest = docs_store.load_manifest()
    if args.prune:
        removed = prune(manifest)
        docs_store.save_manifest(manifest)
        print(f"정리: 잘못 받은 백서 {removed}건 삭제 (색인은 다음 index_docs 때 정리됨)")
    have_item = {d["coin_id"] for d in docs_store.iter_docs() if d.get("is_item_doc")}
    targets = [c for c in coins if c.get("whitepaper") and (args.all or args.coin or c["coin_id"] not in have_item)]
    if args.limit:
        targets = targets[: args.limit]
    print(f"대상 {len(targets)}개 (백서 링크 있음{'' if args.all else ', 자체 문서 없음'})")

    client = whitepaper.make_client()
    saved = empty = failed = skipped = 0
    for c in targets:
        url = c["whitepaper"]
        keyword = f"wp:{url}"
        if docs_store.already_collected(manifest, c["coin_id"], keyword):
            skipped += 1
            continue
        try:
            doc = whitepaper.fetch(client, c, url)
        except (RuntimeError, ValueError, requests.RequestException) as e:
            failed += 1
            print(f"  ! {c['coin_id']}: 받지 못함, 다음 실행 때 재시도 ({type(e).__name__}: {str(e)[:80]})")
            continue
        if doc:
            out = docs_store.save_doc(doc, c, keyword, manifest, is_item_doc=True)
            saved += 1
            pages = f" · {len(doc['pages'])}쪽" if doc.get("pages") else ""
            print(f"  + {c['coin_id']}: {doc['source']} ({len(doc['text']):,}자{pages}) → {out.name}")
        else:
            empty += 1
            print(f"  - {c['coin_id']}: 본문을 읽을 수 없음(스크립트로 그리는 페이지·스캔 PDF·지원하지 않는 형식) {url}")
        docs_store.mark_keyword(manifest, c["coin_id"], keyword)
        docs_store.save_manifest(manifest)
    docs_store.save_manifest(manifest)
    covered = {d["coin_id"] for d in docs_store.iter_docs() if d.get("is_item_doc")}
    total = len(json.loads(path("coins").read_text(encoding="utf-8")))
    print(f"완료: 저장 {saved} · 본문 없음 {empty} · 실패 {failed} · 이미 처리 {skipped}")
    print(f"자체 문서(위키·백서)가 있는 코인: {len(covered)} / {total}  → 다음: python -m scripts.index_docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
