"""근거 검색 및 병합 (F2006 · F2014).

- 선택한 코인의 coin_meta 청크는 검색 없이 항상 근거 1번으로 넣는다.
- coin_docs 는 그 코인으로 범위를 좁혀(where coin_id) 질문과의 의미 유사도로 Top-k 를 찾는다.
- 검색 방식은 settings.retrieval.search_type (similarity | mmr).
- 두 결과를 합치고 (문서, 청크 순번) 기준으로 중복을 없앤다.
"""
from __future__ import annotations

from src.config import settings
from src.data_prep import catalog, items
from src.vectorstore import store


def _meta_context(coin: dict) -> dict:
    col = store.collection("items")
    got = col._collection.get(ids=[coin["coin_id"]], include=["documents", "metadatas"])
    if got["ids"]:
        text, meta = got["documents"][0], got["metadatas"][0]
    else:  # 색인 전이면 같은 규칙으로 즉석 구성
        text, meta = items.index_text(coin), items.metadata(coin)
    return {
        "text": text,
        "title": meta.get("title") or coin["label"],
        "url": meta.get("url", ""),
        "source_type": "coin_meta",
        "source_label": "CoinGecko 메타데이터",
        "key": f"meta:{coin['coin_id']}",
    }


def _doc_contexts(coin_id: str, query: str, top_k: int, search_type: str) -> list[dict]:
    if store.raw_count("docs") == 0:
        return []
    col = store.collection("docs")
    flt = {"coin_id": coin_id}
    r = settings()["retrieval"]
    if search_type == "mmr":
        found = col.max_marginal_relevance_search(
            query, k=top_k, fetch_k=max(top_k, r["mmr_fetch_k"]), lambda_mult=r["mmr_lambda"], filter=flt
        )
    else:
        found = col.similarity_search(query, k=top_k, filter=flt)
    out = []
    for d in found:
        m = d.metadata
        out.append({
            "text": d.page_content,
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "source_type": m.get("source_type", ""),
            "source_label": m.get("source_label") or m.get("source", ""),
            "page": m.get("page"),
            "key": f"{m.get('doc_id')}:{m.get('chunk_index')}",
            "doc": m.get("doc_id"),
            "pos": m.get("chunk_index", 0),
        })
    # 문서는 처음 등장한(가장 관련 높은) 순서, 같은 문서 안에서는 청크 순서대로 묶는다
    rank = {}
    for c in out:
        rank.setdefault(c["doc"], len(rank))
    return sorted(out, key=lambda c: (rank[c["doc"]], c["pos"]))


def retrieve(coin_id: str, query: str, top_k: int | None = None, search_type: str | None = None) -> list[dict]:
    coin = catalog.get(coin_id)
    if coin is None:
        raise KeyError(coin_id)
    r = settings()["retrieval"]
    top_k = top_k or r["top_k"]
    search_type = (search_type or r["search_type"]).lower()
    if search_type not in ("similarity", "mmr"):
        raise ValueError(f"retrieval.search_type 은 similarity 또는 mmr 이어야 합니다: {search_type}")
    merged, seen = [], set()
    for ctx in [_meta_context(coin), *_doc_contexts(coin_id, query or coin["name"], top_k, search_type)]:
        if ctx["key"] in seen:
            continue
        seen.add(ctx["key"])
        merged.append(ctx)
    for i, ctx in enumerate(merged, 1):
        ctx["index"] = i
    return merged
