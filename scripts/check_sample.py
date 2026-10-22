"""최소 가동 샘플 점검 (네트워크·API 키 불필요).

  python -m scripts.check_sample

확인 항목
- F2001: 항목 수 ≥ min_items, 필수 필드, 색인 텍스트 1건 출력
- 출처 매핑: 위키데이터/한·영 위키 연결 수
- F2004/F2005 준비: 저장된 문서 수, 항목 자체 문서 여부, 설정값 기준 청크 수
- NF2007: 문서마다 출처·URL·라이선스 기록 여부
"""
from __future__ import annotations

import json
import sys

from src.config import path, settings
from src.data_prep import docs_store, items

REQUIRED = ["coin_id", "symbol", "name", "market_cap_rank", "snapshot_at", "source"]


def simple_chunks(text: str, size: int, overlap: int) -> int:
    try:
        from src.vectorstore.store import splitter

        return len(splitter().split_text(text))
    except ImportError:  # langchain 미설치 환경: 근사치
        step = max(1, size - overlap)
        return max(1, (len(text) - overlap + step - 1) // step)


def main() -> int:
    cfg = settings()
    ok = True
    if not path("coins").exists():
        print("data/coins.json 이 없습니다. (CoinGecko 약관상 저장소에 올리지 않음)")
        print("먼저 python -m scripts.collect_coins 를 실행하세요.")
        return 1
    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    print(f"[F2001] 항목 {len(coins)}건 (기준 {cfg['coins']['min_items']}건 이상)")
    if len(coins) < cfg["coins"]["min_items"]:
        ok = False
        print("  ✗ 항목 수 부족")
    bad = [c.get("coin_id") for c in coins if any(c.get(k) in (None, "") for k in REQUIRED)]
    print(f"  필수 필드 누락: {len(bad)}건 {bad[:5]}")
    ok &= not bad
    ids = [c["coin_id"] for c in coins]
    dup = len(ids) - len(set(ids))
    print(f"  중복 coin_id: {dup}건")
    ok &= dup == 0
    with_desc = sum(1 for c in coins if c.get("description_ko") or c.get("description_en"))
    with_cat = sum(1 for c in coins if c.get("categories"))
    print(f"  설명 보유 {with_desc}건 · 카테고리 보유 {with_cat}건")
    print("  --- 색인 텍스트 예시 ---")
    for line in items.index_text(coins[0]).splitlines():
        print("   ", line[:160])

    ko = sum(1 for c in coins if c.get("kowiki_title"))
    en = sum(1 for c in coins if c.get("enwiki_title"))
    qid = sum(1 for c in coins if c.get("wikidata_qid"))
    print(f"[출처] 위키데이터 매핑 {qid}건 · 한국어 위키 문서 {ko}건 · 영어 위키 문서 {en}건 · 둘 다 없음 {sum(1 for c in coins if not c.get('kowiki_title') and not c.get('enwiki_title'))}건")

    docs = list(docs_store.iter_docs())
    size, overlap = cfg["chunk"]["size"], cfg["chunk"]["overlap"]
    total_chunks = sum(simple_chunks(d["text"], size, overlap) for d in docs)
    item_docs = sum(1 for d in docs if d.get("is_item_doc"))
    missing_src = [d["title"] for d in docs if not (d.get("url") and d.get("source") and d.get("license"))]
    print(f"[F2004/F2005] 저장 문서 {len(docs)}건 (항목 자체 문서 {item_docs}) → 청크 {total_chunks}개 (size={size}, overlap={overlap})")
    kinds = {}
    for d in docs:
        kinds[d.get("source_type", "?")] = kinds.get(d.get("source_type", "?"), 0) + 1
    covered = {d["coin_id"] for d in docs if d.get("is_item_doc")}
    print(f"[F2016] 출처 종류별 문서: {', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) or '-'}")
    print(f"[전제] 자체 설명 문서(위키·백서)가 있는 코인 {len(covered)} / {len(coins)}"
          + ("" if len(covered) == len(coins) else
             f"  · 나머지 {len(coins) - len(covered)}개는 위키·백서가 없어 CoinGecko 설명만 사용 (D15, 실패 아님)"))
    if not docs:
        print("  미검증: 아직 수집한 문서가 없습니다. python -m scripts.collect_item_docs --limit 20 으로 위키 문서를 받으세요.")
    print(f"[NF2007] 출처/URL/라이선스 누락 문서: {len(missing_src)}건")
    ok &= not missing_src
    manifest = docs_store.load_manifest()
    print(f"[NF2002] manifest 코인 {len(manifest)}개 · 기록된 키워드 {sum(len(v['keywords']) for v in manifest.values())}개")
    print("결과:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
