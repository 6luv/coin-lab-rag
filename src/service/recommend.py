"""조건 기반 코인 탐색 (F2011): coin_meta 의미 검색 후보 → LLM 이 조건에 맞는 코인만 고른다."""
from __future__ import annotations

from src.config import settings
from src.data_prep import catalog, prompts
from src.rag import llm
from src.vectorstore import store

MAX_RESULTS = 6


def recommend(query: str) -> list[dict]:
    n = settings()["retrieval"]["recommend_candidates"]
    found = store.collection("items").similarity_search(query, k=n)
    candidates = [c for c in (catalog.get(d.metadata.get("coin_id")) for d in found) if c]
    if not candidates:
        return []
    listing = "\n".join(
        f"{i}. {c['label']} — 카테고리: {', '.join(c.get('categories') or []) or '-'}"
        f" — {(c.get('description_ko') or c.get('description_en') or '')[:200]}"
        for i, c in enumerate(candidates, 1)
    )
    raw = llm.ask(
        prompts.RECOMMEND_SYSTEM.format(max_results=MAX_RESULTS),
        prompts.RECOMMEND_USER.format(query=query, candidates=listing),
    )
    picked = llm.parse_json(raw, list) or []
    out, seen = [], set()
    for p in picked:
        if not isinstance(p, dict):
            continue
        n_ = p.get("n")
        if isinstance(n_, int) and 1 <= n_ <= len(candidates) and n_ not in seen:
            seen.add(n_)
            c = candidates[n_ - 1]
            out.append({
                "coin_id": c["coin_id"],
                "label": c["label"],
                "symbol": c["symbol"],
                "name": c["name"],
                "market_cap_rank": c.get("market_cap_rank"),
                "categories": c.get("categories") or [],
                "image": c.get("image", ""),
                "reason": str(p.get("reason", ""))[:300],
            })
    return out[:MAX_RESULTS]
