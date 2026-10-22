"""위키데이터·위키백과 클라이언트.

코인 → 위키 문서 매핑 순서: 위키데이터 P5777(CoinMarketCap ID)=CoinGecko id → 이름 slug → 라벨 검색.
본문은 TextExtracts 평문으로 받는다. 라이선스: 위키백과 CC BY-SA 4.0, 위키데이터 CC0.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from src.config import settings
from src.data_prep.http import PoliteClient

WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKI = {"ko": "https://ko.wikipedia.org/w/api.php", "en": "https://en.wikipedia.org/w/api.php"}
SOURCE_NAME = {"ko": "한국어 위키백과", "en": "English Wikipedia"}
CRYPTO_HINT = re.compile(r"crypto|token|blockchain|coin|stablecoin|digital currency|decentrali", re.I)


def make_client() -> PoliteClient:
    return PoliteClient(settings()["http"]["wiki_interval_sec"])


def _haswb(client: PoliteClient, value: str) -> str | None:
    j = client.get_json(
        WIKIDATA,
        {"action": "query", "format": "json", "list": "search", "srlimit": 2,
         "srsearch": f"haswbstatement:P5777={value}"},
    )
    hits = (j or {}).get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def wiki_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


def flat(entry: dict | None) -> dict:
    """source_map.json 항목(중첩 구조) → items.normalize 가 쓰는 평탄한 dict.

    위키데이터 연결 문서를 우선 쓰고, 없으면 accept 로 검토한 검색 후보를 쓴다.
    link_review 가 related/reject 이면 연결 문서를 항목 자체 문서로 쓰지 않는다 (docs/decisions.md D6).
    """
    if not entry:
        return {}
    wd = entry.get("wikidata") or {}
    accepted = (entry.get("candidate_review") or {}).get("decision") == "accept"
    link_ok = (entry.get("link_review") or {}).get("decision", "accept") == "accept"

    def title(lang: str):
        linked = entry.get(f"{lang}wiki")
        if linked:
            return linked["title"] if link_ok else None
        cand = entry.get(f"search_candidate_{lang}")
        return cand["title"] if (accepted and cand) else None

    return {"qid": wd.get("qid"), "label_ko": wd.get("label_ko"), "desc_en": wd.get("desc_en"),
            "kowiki": title("ko"), "enwiki": title("en")}


def map_coin(client: PoliteClient, coin_id: str, name: str) -> dict:
    """코인 1개 → source_map.json 항목 (중첩 구조)."""
    raw = _map_coin(client, coin_id, name)
    entry = {
        "wikidata": {k: raw.get(k) for k in ("qid", "method", "label_ko", "label_en", "desc_en")},
        "kowiki": {"title": raw["kowiki"], "url": wiki_url("ko", raw["kowiki"])} if raw.get("kowiki") else None,
        "enwiki": {"title": raw["enwiki"], "url": wiki_url("en", raw["enwiki"])} if raw.get("enwiki") else None,
    }
    # 라벨 검색으로 찾은 연결은 토큰이 아니라 발행사·플랫폼 문서일 수 있어 사람 검토 대상으로 표시한다.
    if raw.get("method") in ("label_search+desc_filter", "P5777=name_slug") and (raw.get("kowiki") or raw.get("enwiki")):
        entry["link_review"] = {"decision": "accept", "needs_review": True}
    return entry


def _map_coin(client: PoliteClient, coin_id: str, name: str) -> dict:
    qid, method = _haswb(client, coin_id), "P5777=coingecko_id"
    if not qid:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        qid, method = _haswb(client, slug), "P5777=name_slug"
    if not qid:
        j = client.get_json(
            WIKIDATA,
            {"action": "wbsearchentities", "format": "json", "type": "item",
             "language": "en", "limit": 5, "search": name},
        )
        hit = next((s for s in (j or {}).get("search", []) if CRYPTO_HINT.search(s.get("description", ""))), None)
        qid, method = (hit["id"], "label_search+desc_filter") if hit else (None, "not_found")
    if not qid:
        return {"qid": None, "method": "not_found"}
    j = client.get_json(
        WIKIDATA,
        {"action": "wbgetentities", "format": "json", "ids": qid,
         "props": "sitelinks|labels|descriptions", "languages": "ko|en", "sitefilter": "kowiki|enwiki"},
    )
    ent = (j or {}).get("entities", {}).get(qid, {})
    return {
        "qid": qid,
        "method": method,
        "label_ko": ent.get("labels", {}).get("ko", {}).get("value"),
        "label_en": ent.get("labels", {}).get("en", {}).get("value"),
        "desc_en": ent.get("descriptions", {}).get("en", {}).get("value"),
        "kowiki": ent.get("sitelinks", {}).get("kowiki", {}).get("title"),
        "enwiki": ent.get("sitelinks", {}).get("enwiki", {}).get("title"),
    }


def search(client: PoliteClient, query: str, lang: str = "ko", limit: int = 5) -> list[dict]:
    """후보 문서 검색 (F2004: 제목·요약만 받아 선별 프롬프트에 넘긴다)."""
    j = client.get_json(
        WIKI[lang],
        {"action": "query", "format": "json", "list": "search", "srsearch": query,
         "srlimit": limit, "srprop": "snippet|size"},
    )
    rows = (j or {}).get("query", {}).get("search", [])
    return [
        {"page_id": r["pageid"], "title": r["title"],
         "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", "")), "size": r.get("size"), "lang": lang}
        for r in rows
    ]


def fetch_page(client: PoliteClient, title: str, lang: str = "ko") -> dict | None:
    j = client.get_json(
        WIKI[lang],
        {"action": "query", "format": "json", "prop": "extracts|info", "explaintext": 1,
         "inprop": "url", "redirects": 1, "titles": title},
    )
    pages = (j or {}).get("query", {}).get("pages", {})
    page = next(iter(pages.values()), None)
    if not page or "missing" in page or not page.get("extract"):
        return None
    return {
        "page_id": page["pageid"],
        "title": page["title"],
        "url": page["fullurl"],
        "text": page["extract"],
        "lastrevid": page.get("lastrevid"),
        "source": SOURCE_NAME[lang],
        "source_type": f"wikipedia_{lang}",
        "license": "CC BY-SA 4.0",
    }
