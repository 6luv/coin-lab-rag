"""실행 설정 로더.

- 청킹·검색 값은 config/settings.json 에 두고 코드에서 바꾸지 않는다. (F2005, F2006)
- API 키와 연락처는 환경변수(.env)로만 받는다. (NF2003)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"

try:  # python-dotenv 가 없어도 수집 스크립트는 동작하도록 한다.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # 환경변수로 덮어쓸 수 있는 값 (비교 실험용)
    if os.getenv("CHUNK_SIZE"):
        data["chunk"]["size"] = int(os.environ["CHUNK_SIZE"])
    if os.getenv("CHUNK_OVERLAP"):
        data["chunk"]["overlap"] = int(os.environ["CHUNK_OVERLAP"])
    if os.getenv("TOP_K"):
        data["retrieval"]["top_k"] = int(os.environ["TOP_K"])
    if os.getenv("SEARCH_TYPE"):
        data["retrieval"]["search_type"] = os.environ["SEARCH_TYPE"].strip().lower()
    if data["retrieval"]["search_type"] not in ("similarity", "mmr"):
        raise ValueError(f"search_type 은 similarity 또는 mmr 이어야 합니다: {data['retrieval']['search_type']}")
    return data


def path(key: str) -> Path:
    return ROOT / settings()["paths"][key]


def user_agent() -> str:
    contact = os.getenv("CONTACT_EMAIL", "").strip() or "set CONTACT_EMAIL in .env"
    return settings()["http"]["user_agent"].format(contact=contact)


def coingecko_key() -> str | None:
    return os.getenv("COINGECKO_DEMO_API_KEY") or None


def gms_key() -> str | None:
    return os.getenv("GMS_KEY") or os.getenv("OPENAI_API_KEY") or None


def openai_base_url() -> str:
    """비어 있으면 settings.json 의 GMS 주소를 쓴다.

    GMS 는 `/gmsapi/` 뒤 첫 경로를 대상 도메인으로 읽는다. `https://gms.ssafy.io/gmsapi/` 만 적으면
    `.../gmsapi/embeddings` 로 호출돼 403 "Target domain embeddings is not allowed" 가 나므로 OpenAI 경로를 붙인다.
    """
    url = os.getenv("OPENAI_BASE_URL", "").strip() or settings()["models"]["base_url"]
    if url.rstrip("/").endswith("/gmsapi"):
        url = url.rstrip("/") + "/api.openai.com/v1"
    return url


def chat_model() -> str:
    return os.getenv("CHAT_MODEL", "").strip() or settings()["models"]["chat"]


def embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "").strip() or settings()["models"]["embedding"]


def llm_provider() -> str:
    """openai | fake. fake 는 API 키 없이 파이프라인 흐름만 검증할 때 쓴다."""
    return os.getenv("LLM_PROVIDER", "openai").lower()


def embedding_provider() -> str:
    """openai | fake. fake 는 API 키 없이 색인 흐름만 검증할 때 쓴다."""
    return os.getenv("EMBEDDING_PROVIDER", "openai").lower()
