"""코인 항목 정규화와 색인 텍스트 구성 (F2001).

도메인에 묶인 부분(필드 선택, 텍스트 형식)은 이 파일에만 둔다. (NF2005)
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")

DESC_LIMIT = 600  # 색인 텍스트에 넣을 설명 길이 (전체 설명은 문서 컬렉션 쪽에서 다룬다)
_TAG = re.compile(r"<[^>]+>")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG.sub("", value))
    return re.sub(r"\s+", " ", text).strip()


def _first(values) -> str:
    for v in values or []:
        if v:
            return v
    return ""


def logo_url(market: dict, detail: dict) -> str:
    """CoinGecko 로고 URL (상세 small 우선, 없으면 markets image). https 만 허용한다."""
    url = ((detail or {}).get("image") or {}).get("small") or market.get("image") or ""
    return url if url.startswith("https://") else ""


def sparkline(market: dict) -> list[float]:
    """markets 의 7일 시간별 가격(sparkline_in_7d) → 유효숫자 6자리로 줄인 목록."""
    prices = ((market.get("sparkline_in_7d") or {}).get("price")) or []
    return [float(f"{p:.6g}") for p in prices if isinstance(p, (int, float))]


def kst_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return ""


def normalize(market: dict, detail: dict | None, wiki: dict | None, snapshot_at: str) -> dict:
    """markets 1행 + coins/{id} 상세 + 위키 매핑 → 항목 1건."""
    d = detail or {}
    links = d.get("links") or {}
    desc = d.get("description") or {}
    loc = d.get("localization") or {}
    w = wiki or {}
    name_ko = loc.get("ko") or w.get("label_ko") or ""
    desc_en = clean_text(desc.get("en"))[:DESC_LIMIT]
    desc_ko = clean_text(desc.get("ko"))[:DESC_LIMIT]
    # 상세를 아직 못 받은 코인은 위키데이터 한 줄 설명으로 최소한의 검색 단서를 남긴다.
    if desc_en or desc_ko:
        desc_source = "coingecko"
    elif w.get("desc_en"):
        desc_en, desc_source = w["desc_en"], "wikidata"
    else:
        desc_source = ""
    return {
        "coin_id": market["id"],
        "symbol": (market.get("symbol") or "").upper(),
        "name": market.get("name") or "",
        "name_ko": name_ko if name_ko != market.get("name") else "",
        "market_cap_rank": market.get("market_cap_rank"),
        "categories": [c for c in (d.get("categories") or []) if c],
        "genesis_date": d.get("genesis_date"),
        "hashing_algorithm": d.get("hashing_algorithm"),
        "asset_platform_id": d.get("asset_platform_id"),
        "description_ko": desc_ko,
        "description_en": desc_en,
        "description_source": desc_source,
        "detail_collected": detail is not None,
        "image": logo_url(market, d),
        "homepage": _first(links.get("homepage")),
        "whitepaper": links.get("whitepaper") or "",
        "github": _first((links.get("repos_url") or {}).get("github")),
        "explorer": _first(links.get("blockchain_site")),
        "market": {
            "current_price_usd": market.get("current_price"),
            "market_cap_usd": market.get("market_cap"),
            "total_volume_usd": market.get("total_volume"),
            "circulating_supply": market.get("circulating_supply"),
            "total_supply": market.get("total_supply"),
            "max_supply": market.get("max_supply"),
            "ath_usd": market.get("ath"),
            "ath_date": (market.get("ath_date") or "")[:10] or None,
            "change_24h_pct": market.get("price_change_percentage_24h_in_currency"),
            "change_7d_pct": market.get("price_change_percentage_7d_in_currency"),
            "change_30d_pct": market.get("price_change_percentage_30d_in_currency"),
            "last_updated": market.get("last_updated"),
            "sparkline_7d": sparkline(market),
        },
        "wikidata_qid": w.get("qid"),
        "kowiki_title": w.get("kowiki"),
        "enwiki_title": w.get("enwiki"),
        "snapshot_at": snapshot_at,
        "source": "CoinGecko API v3 (Powered by CoinGecko)",
    }


def label(item: dict) -> str:
    ko = f" · {item['name_ko']}" if item.get("name_ko") else ""
    return f"{item['name']} ({item['symbol']}){ko}"


def index_text(item: dict) -> str:
    """항목 1건 → 검색용 텍스트 1개.

    사용자는 이름·심볼·한글명, 카테고리(예: Layer 1, Meme, Stablecoin), 합의/해시 방식,
    출시 시기, 설명 속 키워드로 코인을 찾는다. 가격은 매일 바뀌어 의미 검색에 맞지 않으므로
    텍스트에는 넣지 않고 메타데이터로만 둔다.
    """
    parts = [
        f"코인: {item['name']} ({item['symbol']})",
        f"한국어 이름: {item['name_ko']}" if item.get("name_ko") else "",
        f"시가총액 순위: {item['market_cap_rank']}위 (기준 {kst_date(item['snapshot_at'])} KST)" if item.get("market_cap_rank") else "",
        f"카테고리: {', '.join(item['categories'])}" if item.get("categories") else "",
        f"해시 알고리즘: {item['hashing_algorithm']}" if item.get("hashing_algorithm") else "",
        f"출시일: {item['genesis_date']}" if item.get("genesis_date") else "",
        f"발행 플랫폼: {item['asset_platform_id']}" if item.get("asset_platform_id") else "",
        f"설명: {item['description_ko'] or item['description_en']}" if (item.get("description_ko") or item.get("description_en")) else "",
    ]
    return "\n".join(p for p in parts if p)


def candidate_line(item: dict, desc_chars: int = 200) -> str:
    """조건 탐색(F2011) 선별 프롬프트용 한 줄. 조건 판정에 쓰이는 속성을 빠짐없이 넣는다."""
    parts = [
        item.get("label") or label(item),
        f"시가총액 순위 {item['market_cap_rank']}위" if item.get("market_cap_rank") else "",
        f"카테고리: {', '.join(item['categories'])}" if item.get("categories") else "카테고리: -",
        f"해시 알고리즘: {item['hashing_algorithm']}" if item.get("hashing_algorithm") else "",
        f"출시일: {item['genesis_date']}" if item.get("genesis_date") else "",
        f"발행 플랫폼: {item['asset_platform_id']}" if item.get("asset_platform_id") else "",
        f"설명: {(item.get('description_ko') or item.get('description_en') or '')[:desc_chars]}"
        if (item.get("description_ko") or item.get("description_en")) else "",
    ]
    return " — ".join(p for p in parts if p)


def metadata(item: dict) -> dict:
    """Chroma 메타데이터는 str/int/float/bool 만 허용하므로 평탄화한다."""
    m = item.get("market") or {}
    meta = {
        "coin_id": item["coin_id"],
        "symbol": item["symbol"],
        "name": item["name"],
        "name_ko": item.get("name_ko") or "",
        "market_cap_rank": item.get("market_cap_rank") or 0,
        "categories": ", ".join(item.get("categories") or []),
        "genesis_date": item.get("genesis_date") or "",
        "source_type": "coin_meta",
        "source_label": "CoinGecko 메타데이터",
        "title": label(item),
        "url": f"https://www.coingecko.com/en/coins/{item['coin_id']}",
        "snapshot_at": item.get("snapshot_at") or "",
    }
    if m.get("market_cap_usd") is not None:
        meta["market_cap_usd"] = float(m["market_cap_usd"])
    return meta
