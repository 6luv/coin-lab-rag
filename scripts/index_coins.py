"""F2002: 코인 메타데이터 색인 (coin_meta 컬렉션, 코인당 1청크).

  python -m scripts.index_coins          # GMS 임베딩
  EMBEDDING_PROVIDER=fake python -m scripts.index_coins   # 키 없이 흐름 확인
"""
from __future__ import annotations

import json

from src.config import path
from src.data_prep import items
from src.vectorstore import store


def main() -> int:
    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    col = store.collection("items")
    ids = [c["coin_id"] for c in coins]
    texts = [items.index_text(c) for c in coins]
    metas = [items.metadata(c) for c in coins]
    for start in range(0, len(ids), 64):  # 배치로 나눠 임베딩 요청 크기를 제한한다
        col.add_texts(texts=texts[start:start + 64], metadatas=metas[start:start + 64], ids=ids[start:start + 64])
    # 순위 밖으로 빠진 코인은 색인에서 지운다 → 색인 건수 = 로드한 항목 수 (검증 4.1)
    stale = sorted(set(col._collection.get(include=[])["ids"]) - set(ids))
    if stale:
        col._collection.delete(ids=stale)
        print(f"목록에서 빠진 코인 {len(stale)}건 삭제: {', '.join(stale[:5])}{' ...' if len(stale) > 5 else ''}")
    print(f"로드한 코인 {len(coins)}건 · coin_meta 청크 {col._collection.count()}건")
    print("--- 색인 텍스트 예시 (1건) ---")
    print(texts[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
