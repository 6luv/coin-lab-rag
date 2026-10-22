"""source_map 해석(wiki.flat)과 스냅샷 데이터 무결성 확인."""
import json

import pytest

from src.config import path
from src.data_prep import wiki


def test_flat_prefers_linked_then_accepted_candidate():
    linked = {"wikidata": {"qid": "Q1"}, "kowiki": {"title": "비트코인"}, "enwiki": None,
              "search_candidate_en": {"title": "X"}, "candidate_review": {"decision": "accept"}}
    assert wiki.flat(linked) == {"qid": "Q1", "label_ko": None, "desc_en": None, "kowiki": "비트코인", "enwiki": "X"}
    rejected = {"wikidata": {}, "kowiki": None, "enwiki": None,
                "search_candidate_en": {"title": "Canton of Zug"}, "candidate_review": {"decision": "reject"}}
    assert wiki.flat(rejected)["enwiki"] is None
    assert wiki.flat(None) == {}


def test_snapshot_consistency():
    if not path("coins").exists():  # git 에 올리지 않는 파일: collect_coins 실행 후에만 검사
        pytest.skip("data/coins.json 없음 — python -m scripts.collect_coins 실행 후 검사")
    coins = json.loads(path("coins").read_text(encoding="utf-8"))
    smap = json.loads(path("source_map").read_text(encoding="utf-8"))
    assert len(coins) >= 100
    for c in coins:
        f = wiki.flat(smap[c["coin_id"]])
        assert (c["kowiki_title"], c["enwiki_title"]) == (f["kowiki"], f["enwiki"])


def test_wiki_url_encoding():
    assert wiki.wiki_url("ko", "테더 (암호화폐)").startswith("https://ko.wikipedia.org/wiki/%ED%85%8C%EB%8D%94_%28")
