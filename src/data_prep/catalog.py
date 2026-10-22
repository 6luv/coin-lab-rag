"""코인 목록(data/coins.json) 조회. 파일이 바뀌면 다시 읽는다."""
from __future__ import annotations

import json

from src.config import path
from src.data_prep import items

_cache: dict = {"mtime": None, "coins": [], "by_id": {}}


def coins() -> list[dict]:
    p = path("coins")
    if not p.exists():
        return []
    mtime = p.stat().st_mtime
    if _cache["mtime"] != mtime:
        rows = json.loads(p.read_text(encoding="utf-8"))
        for r in rows:
            r["label"] = items.label(r)
        _cache.update(mtime=mtime, coins=rows, by_id={r["coin_id"]: r for r in rows})
    return _cache["coins"]


def get(coin_id: str) -> dict | None:
    coins()
    return _cache["by_id"].get(coin_id)
