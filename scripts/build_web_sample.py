"""data/coins.json → web/sample/coins_sample.js (서버 없이 화면을 확인하는 샘플 모드용).

  python -m scripts.build_web_sample
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.config import ROOT, path, settings
from src.data_prep import docs_store

FIELDS = [
    "coin_id", "symbol", "name", "name_ko", "market_cap_rank", "categories", "genesis_date",
    "hashing_algorithm", "image", "description_ko", "description_en", "homepage", "whitepaper", "github",
    "market", "kowiki_title", "enwiki_title", "snapshot_at",
]


def main() -> int:
    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    manifest = docs_store.load_manifest()
    rows = []
    for c in coins:
        row = {k: c.get(k) for k in FIELDS}
        titles = manifest.get(c["coin_id"], {}).get("titles")
        if titles:
            row["doc_titles"] = titles
        rows.append(row)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attribution": "Data and logos provided by CoinGecko (https://www.coingecko.com)",
        "disclaimer": settings()["domain"]["disclaimer"],
        "coins": rows,
    }
    out = ROOT / "web" / "sample" / "coins_sample.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "// 자동 생성 파일: python -m scripts.build_web_sample\n"
        "window.COIN_SAMPLE = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"{out} ← 코인 {len(rows)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
