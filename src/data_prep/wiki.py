"""위키데이터·위키백과 클라이언트.

코인 → 위키 문서 매핑 순서: 위키데이터 P5777(CoinMarketCap ID)=CoinGecko id → 이름 slug → 라벨 검색.
본문은 TextExtracts 평문으로 받는다. 라이선스: 위키백과 CC BY-SA 4.0, 위키데이터 CC0.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from src.config import contact, settings
from src.data_prep.http import PoliteClient

WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKI = {"ko": "https://ko.wikipedia.org/w/api.php", "en": "https://en.wikipedia.org/w/api.php"}
SOURCE_NAME = {"ko": "한국어 위키백과", "en": "English Wikipedia"}
CRYPTO_HINT = re.compile(r"crypto|token|blockchain|coin|stablecoin|digital currency|decentrali", re.I)


CONTACT_MISSING = (
    "CONTACT_EMAIL(이메일 또는 프로젝트 URL)이 .env 에 없어 위키 문서를 수집하지 않습니다. "
    "위키미디어 User-Agent 정책상 연락처가 필요합니다 (NF2006)."
)


class MissingContactError(Exception):
    """연락처 없이 위키미디어 API 를 부르려 할 때. 네트워크 오류(RuntimeError)와 구분한다."""


def make_client() -> PoliteClient:
    if not contact():
        raise MissingContactError(CONTACT_MISSING)
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


# --- 위키데이터 연결이 없는 코인의 자체 문서 찾기 (F2004 우선 규칙) ---
_ITEM_HINT = re.compile(r"암호화폐|가상자산|가상화폐|코인|토큰|블록체인|스테이블코인|crypto|token|blockchain|coin|stablecoin|decentrali", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_.·()]+", "", text or "").lower()


def is_item_page(coin: dict, row: dict) -> bool:
    """검색 결과 한 건이 그 코인 자체를 다룬 문서인지.

    제목(괄호 앞)이 코인 이름·한글명·심볼과 같고, 괄호 설명이나 요약에 암호화폐 단서가 있어야 한다.
    이름만 같은 동음이의 문서(예: Rain → 가수)와 발행사·거래소 문서(이름이 다름)는 걸러진다. (D6 · D12)
    """
    title = row.get("title", "")
    base = re.sub(r"\s*\(.*\)\s*$", "", title)
    names = {_norm(x) for x in (coin.get("name"), coin.get("name_ko"), coin.get("symbol")) if x}
    if _norm(base) not in names:
        return False
    paren = re.search(r"\(([^)]*)\)\s*$", title)
    return bool(_ITEM_HINT.search(row.get("snippet", "")) or (paren and _ITEM_HINT.search(paren.group(1))))


def find_item_page(client: PoliteClient, coin: dict) -> dict | None:
    """한국어 → 영어 위키백과에서 코인 자체 문서를 찾아 본문을 받는다. 없으면 None."""
    queries = (("ko", f"{coin.get('name_ko') or coin['name']} 암호화폐"), ("en", f"{coin['name']} cryptocurrency"))
    for lang, query in queries:
        for row in search(client, query, lang, 5):
            if is_item_page(coin, row):
                page = fetch_page(client, row["title"], lang)
                if page:
                    return page
    return None
