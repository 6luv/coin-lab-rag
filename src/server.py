"""Coin Lab API 서버 (F2009 ~ F2013).

  python -m src.server            # http://127.0.0.1:8000
  python -m src.server --port 8080

화면(web/)과 JSON API 를 함께 제공한다. 오류 응답에는 사용자용 문장만 담고
키·프롬프트·스택트레이스는 서버 로그에만 남긴다 (NF2003 · NF2004).
"""
from __future__ import annotations

import argparse
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import ROOT, chat_model, contact, gms_key, settings
from src.data_prep import catalog, docs_store
from src.rag import collect as collector
from src.rag import graph
from src.service import recommend as recommender
from src.vectorstore import store
from src.vectorstore.store import MissingKeyError

log = logging.getLogger("coinlab")
app = FastAPI(title="Coin Lab API")

PUBLIC_FIELDS = [
    "coin_id", "symbol", "name", "name_ko", "label", "market_cap_rank", "categories", "genesis_date",
    "hashing_algorithm", "asset_platform_id", "image", "description_ko", "description_en", "homepage",
    "whitepaper", "github", "market", "kowiki_title", "enwiki_title", "snapshot_at",
]


class QuestionIn(BaseModel):
    question: str = Field("", max_length=500)


class AskIn(BaseModel):
    coin_id: str = Field(..., max_length=120)
    question: str = Field(..., min_length=1, max_length=500)


class ClaimIn(BaseModel):
    claim: str = Field("", max_length=500)


class QueryIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)


@app.exception_handler(MissingKeyError)
def _missing_key(_: Request, exc: MissingKeyError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
def _unexpected(_: Request, exc: Exception):
    log.exception("처리 중 오류")
    return JSONResponse(status_code=500, content={"detail": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요."})


def _public(coin: dict, manifest: dict | None = None) -> dict:
    row = {k: coin.get(k) for k in PUBLIC_FIELDS}
    if manifest is not None:
        row["doc_titles"] = manifest.get(coin["coin_id"], {}).get("titles", [])
    return row


def _coin_or_404(coin_id: str) -> dict:
    coin = catalog.get(coin_id)
    if coin is None:
        raise HTTPException(404, "코인을 찾을 수 없습니다.")
    return coin


@app.get("/api/status")
def status():
    return {
        "api_key": bool(gms_key()),
        "contact": bool(contact()),  # NF2006: 없으면 위키 문서 수집을 하지 않는다
        "chat_model": chat_model(),
        "coins": len(catalog.coins()),
        "indexes": {"coin_meta": store.raw_count("items"), "coin_docs": store.raw_count("docs")},
        "disclaimer": settings()["domain"]["disclaimer"],
    }


@app.get("/api/coins")
def list_coins():
    manifest = docs_store.load_manifest()
    return [_public(c, manifest) for c in catalog.coins()]


@app.get("/api/coins/{coin_id}")
def get_coin(coin_id: str):
    return _public(_coin_or_404(coin_id), docs_store.load_manifest())


@app.post("/api/coins/{coin_id}/collect")
def collect(coin_id: str, body: QuestionIn):
    _coin_or_404(coin_id)
    return collector.collect(coin_id, body.question)


@app.post("/api/ask")
def ask(body: AskIn):
    _coin_or_404(body.coin_id)
    if not body.question.strip():
        raise HTTPException(422, "질문을 입력하세요.")
    return graph.run(body.coin_id, body.question.strip(), "ask")


@app.post("/api/coins/{coin_id}/brief")
def brief(coin_id: str):
    _coin_or_404(coin_id)
    return graph.run(coin_id, "", "brief")


@app.post("/api/coins/{coin_id}/factcheck")
def factcheck(coin_id: str, body: ClaimIn):
    _coin_or_404(coin_id)
    if not body.claim.strip():
        raise HTTPException(422, "확인할 주장을 입력하세요.")
    return graph.run(coin_id, body.claim.strip(), "factcheck")


@app.post("/api/recommend")
def recommend(body: QueryIn):
    if not body.query.strip():
        raise HTTPException(422, "찾을 조건을 입력하세요.")
    return {"results": recommender.recommend(body.query.strip())}


# 화면: API 경로 뒤에 붙여 /api/* 가 가려지지 않게 한다
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import uvicorn

    print(f"Coin Lab: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
