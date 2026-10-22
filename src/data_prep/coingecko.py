"""CoinGecko 공개 API 클라이언트. 이용 조건은 docs/data_sources.md 참고.

Demo 키(COINGECKO_DEMO_API_KEY)가 있으면 x-cg-demo-api-key 헤더로 보낸다.
"""
from __future__ import annotations

from src.config import coingecko_key, settings
from src.data_prep.http import PoliteClient

BASE = "https://api.coingecko.com/api/v3"


def make_client() -> PoliteClient:
    cfg = settings()["http"]
    key = coingecko_key()
    headers = {"x-cg-demo-api-key": key} if key else None
    interval = cfg["coingecko_interval_with_key_sec"] if key else cfg["coingecko_interval_sec"]
    return PoliteClient(interval, headers=headers, wait_429_sec=cfg["coingecko_429_wait_sec"])


def ping(client: PoliteClient) -> dict:
    return client.get_json(f"{BASE}/ping")


def markets(client: PoliteClient, count: int, vs_currency: str = "usd") -> list[dict]:
    """시가총액 순 상위 count 개 (한 페이지 최대 250)."""
    out: list[dict] = []
    page = 1
    while len(out) < count:
        per_page = min(250, count - len(out))
        rows = client.get_json(
            f"{BASE}/coins/markets",
            params={
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "true",  # 7일 시간별 가격 (화면 차트용)
                "price_change_percentage": "24h,7d,30d",
            },
        )
        if not rows:
            break
        out.extend(rows)
        page += 1
    return out[:count]


def coin_detail(client: PoliteClient, coin_id: str) -> dict | None:
    return client.get_json(
        f"{BASE}/coins/{coin_id}",
        params={
            "localization": "true",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
    )
