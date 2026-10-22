"""F2001 · F2005 단위 테스트 (네트워크 불필요)."""
from src.data_prep import items

MARKET = {
    "id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1,
    "current_price": 100.0, "market_cap": 1e12, "ath": 120.0, "ath_date": "2025-10-06T00:00:00Z",
    "price_change_percentage_24h_in_currency": 1.5,
}
DETAIL = {
    "categories": ["Layer 1 (L1)", None, "Proof of Work (PoW)"],
    "genesis_date": "2009-01-03",
    "hashing_algorithm": "SHA-256",
    "description": {"en": "<a href='x'>Bitcoin</a> is the first &amp; best", "ko": ""},
    "localization": {"ko": "비트코인"},
    "links": {"homepage": ["", "https://bitcoin.org"], "repos_url": {"github": ["https://github.com/bitcoin/bitcoin"]}},
}
WIKI = {"qid": "Q131723", "kowiki": "비트코인", "enwiki": "Bitcoin"}


def test_normalize_cleans_and_maps():
    item = items.normalize(MARKET, DETAIL, WIKI, "2026-10-22T00:00:00+00:00")
    assert item["symbol"] == "BTC"
    assert item["name_ko"] == "비트코인"
    assert item["categories"] == ["Layer 1 (L1)", "Proof of Work (PoW)"]
    assert item["description_en"] == "Bitcoin is the first & best"
    assert item["homepage"] == "https://bitcoin.org"
    assert item["kowiki_title"] == "비트코인"
    assert item["market"]["ath_date"] == "2025-10-06"


def test_normalize_without_detail():
    item = items.normalize(MARKET, None, None, "2026-10-22T00:00:00+00:00")
    assert item["categories"] == [] and item["kowiki_title"] is None


def test_index_text_has_search_fields_but_not_price():
    item = items.normalize(MARKET, DETAIL, WIKI, "2026-10-22T00:00:00+00:00")
    text = items.index_text(item)
    for needle in ["Bitcoin (BTC)", "비트코인", "Layer 1", "SHA-256", "2009-01-03", "설명:"]:
        assert needle in text
    assert "100.0" not in text  # 가격은 텍스트에 넣지 않는다


def test_metadata_is_flat():
    meta = items.metadata(items.normalize(MARKET, DETAIL, WIKI, "2026-10-22T00:00:00+00:00"))
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())
    assert meta["source_type"] == "coin_meta"


def test_logo_url_prefers_detail_small_and_requires_https():
    detail = {"image": {"small": "https://coin-images.coingecko.com/coins/images/1/small/bitcoin.png"}}
    assert items.logo_url({"image": "https://x/large.png"}, detail).endswith("/small/bitcoin.png")
    assert items.logo_url({"image": "https://x/large.png"}, {}) == "https://x/large.png"
    assert items.logo_url({"image": "javascript:alert(1)"}, {}) == ""
    assert items.normalize(MARKET, DETAIL, WIKI, "2026-10-22T00:00:00+00:00")["image"] == ""


def test_sparkline_and_kst_date():
    market = {**MARKET, "sparkline_in_7d": {"price": [84179.123456789, None, 84200.5]}, "last_updated": "2026-10-22T00:32:00Z"}
    item = items.normalize(market, DETAIL, WIKI, "2026-10-21T16:30:00+00:00")
    assert item["market"]["sparkline_7d"] == [84179.1, 84200.5]
    assert item["market"]["last_updated"] == "2026-10-22T00:32:00Z"
    assert items.kst_date("2026-10-21T16:30:00+00:00") == "2026-10-22"  # UTC 16:30 = KST 다음날 01:30
    assert "기준 2026-10-22 KST" in items.index_text(item)
