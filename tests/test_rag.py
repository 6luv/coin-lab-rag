"""RAG 파이프라인·서버 테스트: 가짜 LLM·가짜 임베딩·가짜 위키로 네트워크 없이 돌린다."""
import json

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("fastapi")

from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from src.config import settings  # noqa: E402
from src.data_prep import catalog, docs_store  # noqa: E402
from src.rag import collect, graph, llm  # noqa: E402

COINS = [
    {"coin_id": "ethereum", "symbol": "ETH", "name": "Ethereum", "name_ko": "이더리움", "market_cap_rank": 2,
     "categories": ["Layer 1 (L1)"], "description_ko": "스마트 계약 플랫폼", "description_en": "",
     "snapshot_at": "2026-10-22T00:32:46Z", "source": "CoinGecko", "kowiki_title": "이더리움", "enwiki_title": "Ethereum",
     "market": {"market_cap_usd": 3e11}, "image": ""},
    {"coin_id": "rain", "symbol": "RAIN", "name": "Rain", "name_ko": "", "market_cap_rank": 21,
     "categories": ["Options"], "description_ko": "", "description_en": "Arbitrum options protocol",
     "snapshot_at": "2026-10-22T00:32:46Z", "source": "CoinGecko", "kowiki_title": None, "enwiki_title": None,
     "market": {}, "image": ""},
]
LONG = "이더리움은 2022년 9월 더 머지로 작업증명에서 지분증명으로 전환했다. " * 30


def page(title, lang="ko", pid=1):
    return {"page_id": pid, "title": title, "url": f"https://{lang}.wikipedia.org/wiki/{pid}", "text": LONG,
            "source": "한국어 위키백과" if lang == "ko" else "English Wikipedia", "source_type": f"wikipedia_{lang}",
            "license": "CC BY-SA 4.0", "lastrevid": 1}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("CONTACT_EMAIL", "test@example.com")
    for key, rel in {"coins": "coins.json", "docs_dir": "docs", "manifest": "docs/manifest.json",
                     "chroma_dir": "chroma", "source_map": "source_map.json"}.items():
        monkeypatch.setitem(settings()["paths"], key, str(tmp_path / rel))
    (tmp_path / "coins.json").write_text(json.dumps(COINS, ensure_ascii=False), encoding="utf-8")
    catalog._cache.update(mtime=None)
    calls = {"search": [], "fetch": []}

    def search(_c, q, lang="ko", limit=5):
        calls["search"].append(q)
        return [{"page_id": 10, "title": "지분증명", "snippet": "합의 알고리즘", "size": 1, "lang": "ko"},
                {"page_id": 11, "title": "레인 (가수)", "snippet": "대한민국의 가수", "size": 1, "lang": "ko"}]

    def fetch(_c, title, lang="ko"):
        calls["fetch"].append(title)
        return page(title, lang, {"이더리움": 1, "지분증명": 10}.get(title, 99))

    monkeypatch.setattr(collect.wiki, "search", search)
    monkeypatch.setattr(collect.wiki, "fetch_page", fetch)
    monkeypatch.setattr(collect, "_wiki_client", object())
    monkeypatch.setattr(graph, "_graph", None)
    yield calls
    llm.set_llm(None)


def script(*responses):
    llm.set_llm(FakeListChatModel(responses=list(responses)))


def test_parse_json_handles_fences_and_noise():
    assert llm.parse_json('```json\n["a", "b"]\n```', list) == ["a", "b"]
    assert llm.parse_json('검색어: ["지분증명"] 입니다', list) == ["지분증명"]
    assert llm.parse_json("모르겠습니다", list) is None
    assert llm.parse_json('{"a": 1}', list) is None


def test_collect_item_doc_first_then_selected_and_cache(env):
    script('["지분증명", "레인"]', "[1]")
    out = collect.collect("ethereum", "언제 지분증명으로 바뀌었나?")
    assert out["added_titles"][0] == "이더리움"           # 항목 자체 문서가 먼저, 항상
    assert "지분증명" in out["added_titles"]               # 프롬프트2가 고른 문서
    assert "레인 (가수)" not in out["added_titles"]        # 고르지 않은 후보는 본문을 받지 않음
    assert env["fetch"] == ["이더리움", "지분증명"]
    docs = list(docs_store.iter_docs())
    assert {d["title"] for d in docs} == {"이더리움", "지분증명"}
    assert next(d for d in docs if d["title"] == "이더리움")["is_item_doc"] is True

    script('["지분증명", "레인"]', "[]")                    # 같은 질문 다시: 검색어 재수집 안 함
    again = collect.collect("ethereum", "언제 지분증명으로 바뀌었나?")
    assert again["added_titles"] == [] and set(again["skipped_keywords"]) == {"지분증명", "레인"}
    assert len(env["search"]) == 2


def test_collect_bad_llm_output_selects_nothing(env):
    script("검색어를 모르겠어요", "번호 없음")
    out = collect.collect("rain", "옵션 프로토콜 구조는?")
    assert out["added_titles"] == [] and out["errors"] == 1


def test_select_parse_failure_keeps_keyword_open_then_retries(env):
    script('["지분증명"]', "invalid JSON output")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["errors"] == 1 and "지분증명" not in out["added_titles"]
    assert "q:지분증명" not in docs_store.load_manifest()["ethereum"]["keywords"]

    script('["지분증명"]', "[1]")                            # 정상 응답으로 재시도
    again = collect.collect("ethereum", "지분증명 전환")
    assert again["skipped_keywords"] == [] and "지분증명" in again["added_titles"]
    assert "q:지분증명" in docs_store.load_manifest()["ethereum"]["keywords"]


def test_select_empty_array_marks_keyword_done(env):
    script('["지분증명"]', "[]")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["errors"] == 0
    assert "q:지분증명" in docs_store.load_manifest()["ethereum"]["keywords"]


def test_graph_has_two_nodes_and_cites_only_used_sources(env):
    nodes = set(graph.build_graph().get_graph().nodes)
    assert {"retrieve", "generate"} <= nodes
    script('["지분증명"]', "[1]")
    collect.collect("ethereum", "지분증명 전환")
    script("2022년 9월 더 머지로 지분증명으로 전환했습니다 [근거 2]. 시가총액 2위입니다 [근거 1].")
    out = graph.run("ethereum", "언제 지분증명으로 바뀌었나?")
    assert out["cited"] is True
    assert [s["index"] for s in out["sources"]] == [1, 2]
    assert out["sources"][0]["source_type"] == "coin_meta"
    assert out["sources"][1]["source_type"] == "wikipedia_ko"


def test_graph_no_citation_reports_uncited(env):
    script("제공된 문서에서 확인되지 않습니다.")
    out = graph.run("rain", "창업자는 누구인가?")
    assert out == {"answer": "제공된 문서에서 확인되지 않습니다.", "sources": [], "cited": False}


def test_cited_numbers_parsing():
    assert graph.cited_numbers("a [근거 1, 3] b [근거2] c［근거 4］") == {1, 2, 3, 4}


def test_server_endpoints(env):
    from fastapi.testclient import TestClient

    from src import server

    c = TestClient(server.app)
    st = c.get("/api/status").json()
    assert st["coins"] == 2 and "disclaimer" in st and "coin_meta" in st["indexes"]
    assert [x["coin_id"] for x in c.get("/api/coins").json()] == ["ethereum", "rain"]
    assert c.get("/api/coins/nope").status_code == 404
    assert c.post("/api/ask", json={"coin_id": "ethereum", "question": ""}).status_code == 422
    assert c.post("/api/coins/ethereum/factcheck", json={"claim": " "}).status_code == 422

    script('["지분증명"]', "[1]")
    col = c.post("/api/coins/ethereum/collect", json={"question": "지분증명 전환"}).json()
    assert "이더리움" in col["titles"]
    script("지분증명으로 전환했습니다 [근거 2].")
    ans = c.post("/api/ask", json={"coin_id": "ethereum", "question": "합의 방식은?"}).json()
    assert ans["cited"] and ans["sources"][0]["index"] == 2
    script("판정: 사실\n2022년에 전환했습니다 [근거 2].")
    fc = c.post("/api/coins/ethereum/factcheck", json={"claim": "이더리움은 지분증명이다"}).json()
    assert fc["answer"].startswith("판정: 사실")
    detail = c.get("/api/coins/ethereum").json()
    assert "지분증명" in detail["doc_titles"]

    script('[{"n": 1, "reason": "레이어1 스마트 계약 플랫폼"}, {"n": 99}]')
    from src.vectorstore import store
    from src.data_prep import items
    col_items = store.collection("items")
    col_items.add_texts([items.index_text(x) for x in COINS], metadatas=[items.metadata(x) for x in COINS],
                        ids=[x["coin_id"] for x in COINS])
    rec = c.post("/api/recommend", json={"query": "스마트 계약 플랫폼"}).json()["results"]
    assert len(rec) == 1 and rec[0]["reason"].startswith("레이어1")
    assert c.get("/").status_code == 200  # 화면 제공


def test_server_hides_internal_errors(env, monkeypatch):
    from fastapi.testclient import TestClient

    from src import server

    def boom(*a, **k):
        raise RuntimeError("secret prompt text and key sk-123")

    monkeypatch.setattr(server.graph, "run", boom)
    r = TestClient(server.app, raise_server_exceptions=False).post("/api/ask", json={"coin_id": "ethereum", "question": "q"})
    assert r.status_code == 500 and "sk-123" not in r.text and "prompt" not in r.text


def test_item_doc_reindexed_when_only_in_manifest(env):
    from src.vectorstore import store

    script("[]")
    collect.collect("ethereum", "")                       # 자체 문서 수집·색인
    col = store.collection("docs")
    col.reset_collection()                                # 색인만 사라진 상황 (manifest·파일은 남음)
    assert store.raw_count("docs") == 0
    collect.collect("ethereum", "")
    assert store.raw_count("docs") > 0
    assert env["fetch"] == ["이더리움"]                     # 위키를 다시 부르지 않고 저장 파일로 재색인


def test_item_doc_falls_back_to_english(env, monkeypatch):
    def fetch(_c, title, lang="ko"):
        env["fetch"].append((title, lang))
        return None if lang == "ko" else page(title, lang, 7)

    monkeypatch.setattr(collect.wiki, "fetch_page", fetch)
    out = collect.collect("ethereum", "")
    assert env["fetch"] == [("이더리움", "ko"), ("Ethereum", "en")]
    assert out["added_titles"] == ["Ethereum"]


def test_llm_failure_keeps_manifest_and_skips_collection(env):
    class Broken:
        def invoke(self, *_a, **_k):
            raise ConnectionError("gms down")

    llm.set_llm(Broken())
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["added_titles"] == ["이더리움"] and out["errors"] == 1
    assert "이더리움" in docs_store.load_manifest()["ethereum"]["titles"]


def test_failed_fetch_keyword_not_cached(env, monkeypatch):
    script('["지분증명"]', "[1]")
    collect.collect("ethereum", "")                        # 자체 문서 먼저

    def fetch(_c, title, lang="ko"):
        raise RuntimeError("timeout")

    monkeypatch.setattr(collect.wiki, "fetch_page", fetch)
    script('["지분증명"]', "[1]")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["errors"] == 1
    assert "q:지분증명" not in docs_store.load_manifest()["ethereum"]["keywords"]


def test_coin_without_wiki_link_searches_coin_name_first(env):
    script('["옵션"]', "[]")
    out = collect.collect("rain", "옵션 구조는?")
    assert env["search"][0] == "Rain 암호화폐" and out["keywords"][0] == "Rain 암호화폐"


def test_cited_range_and_mmr(env, monkeypatch):
    assert graph.cited_numbers("[근거 1-3] [근거 5~6]") == {1, 2, 3, 5, 6}
    script('["지분증명"]', "[1]")
    collect.collect("ethereum", "지분증명 전환")
    monkeypatch.setitem(settings()["retrieval"], "search_type", "mmr")
    from src.rag.retrieve import retrieve
    ctx = retrieve("ethereum", "지분증명")
    assert ctx[0]["source_type"] == "coin_meta" and len(ctx) > 1
    monkeypatch.setitem(settings()["retrieval"], "search_type", "typo")
    with pytest.raises(ValueError):
        retrieve("ethereum", "지분증명")


def test_blank_question_rejected(env):
    from fastapi.testclient import TestClient

    from src import server

    c = TestClient(server.app)
    assert c.post("/api/ask", json={"coin_id": "ethereum", "question": "   "}).status_code == 422
    assert c.post("/api/recommend", json={"query": "  "}).status_code == 422


# --- Codex 검증(2026-10-22) 실패 복구 회귀 테스트 ---

def _doc_chunks(coin_id, doc_id):
    from src.vectorstore import store

    return store.collection("docs")._collection.get(
        where={"$and": [{"coin_id": coin_id}, {"doc_id": doc_id}]}, include=[])["ids"]


def test_index_doc_keeps_old_chunks_when_embedding_fails(env, monkeypatch):
    from src.vectorstore import store

    col = store.collection("docs")
    doc = {**page("이더리움"), "doc_id": "wikipedia_ko-1", "coin_id": "ethereum", "related_coin": "Ethereum"}
    n = store.index_doc(col, doc)
    assert n >= 2 and len(_doc_chunks("ethereum", "wikipedia_ko-1")) == n

    def boom(*a, **k):
        raise RuntimeError("403")

    monkeypatch.setattr(type(col), "add_texts", boom)
    with pytest.raises(RuntimeError):
        store.index_doc(col, {**doc, "text": "짧은 새 본문"})
    assert len(_doc_chunks("ethereum", "wikipedia_ko-1")) == n   # 이전 색인 유지


def test_index_doc_removes_stale_chunks_after_success(env):
    from src.vectorstore import store

    col = store.collection("docs")
    doc = {**page("이더리움"), "doc_id": "wikipedia_ko-1", "coin_id": "ethereum", "related_coin": "Ethereum"}
    assert store.index_doc(col, doc) >= 2
    assert store.index_doc(col, {**doc, "text": "짧은 새 본문"}) == 1
    assert _doc_chunks("ethereum", "wikipedia_ko-1") == ["ethereum:wikipedia_ko-1:0"]


def test_index_failure_does_not_mark_keyword_and_recovers(env, monkeypatch):
    from src.vectorstore import store

    real = store.index_doc

    def fail_for_question_doc(col, doc):
        if doc["doc_id"] == "wikipedia_ko-10":
            raise RuntimeError("embedding 403")
        return real(col, doc)

    monkeypatch.setattr(store, "index_doc", fail_for_question_doc)
    script('["지분증명"]', "[1]")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["errors"] == 1 and "지분증명" not in out["added_titles"]
    assert "q:지분증명" not in docs_store.load_manifest()["ethereum"]["keywords"]
    assert _doc_chunks("ethereum", "wikipedia_ko-10") == []

    monkeypatch.setattr(store, "index_doc", real)            # 장애 해소
    script('["지분증명"]', "[]")
    again = collect.collect("ethereum", "지분증명 전환")
    assert again["skipped_keywords"] == []                    # 검색어를 다시 시도
    assert _doc_chunks("ethereum", "wikipedia_ko-10")         # 저장 파일로 재색인 복구
    assert "q:지분증명" in docs_store.load_manifest()["ethereum"]["keywords"]


def test_partial_fetch_failure_keeps_keyword_open(env, monkeypatch):
    def search(_c, q, lang="ko", limit=5):
        return [{"page_id": 10, "title": "지분증명", "snippet": "", "size": 1, "lang": "ko"},
                {"page_id": 12, "title": "더 머지", "snippet": "", "size": 1, "lang": "ko"}]

    def fetch(_c, title, lang="ko"):
        if title == "더 머지":
            raise RuntimeError("timeout")
        return page(title, lang, {"이더리움": 1, "지분증명": 10}[title])

    monkeypatch.setattr(collect.wiki, "search", search)
    monkeypatch.setattr(collect.wiki, "fetch_page", fetch)
    script('["지분증명"]', "[1, 2]")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["errors"] == 1 and "지분증명" in out["added_titles"]
    assert "q:지분증명" not in docs_store.load_manifest()["ethereum"]["keywords"]


def test_same_title_different_language_are_separate_files(env):
    coin = {"coin_id": "ethereum", "name": "Ethereum"}
    manifest = {}
    a = docs_store.save_doc({**page("Same Title", "ko", 123)}, coin, "k", manifest, False)
    b = docs_store.save_doc({**page("Same Title", "en", 456)}, coin, "k", manifest, False)
    assert a != b and a.exists() and b.exists()
    assert manifest["ethereum"]["page_ids"] == ["wikipedia_ko-123", "wikipedia_en-456"]
    assert manifest["ethereum"]["keywords"] == []             # 저장만으로는 검색어 완료 아님
    assert {d["doc_id"] for d in docs_store.iter_docs()} == {"wikipedia_ko-123", "wikipedia_en-456"}


def test_migrate_legacy_filenames_and_manifest(env):
    legacy = docs_store.docs_dir() / "ethereum_이더리움.json"
    rec = {**page("이더리움"), "doc_id": "wikipedia_ko-1", "coin_id": "ethereum", "related_coin": "Ethereum"}
    legacy.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    manifest = {"ethereum": {"keywords": ["item:ko:이더리움"], "titles": ["이더리움", "사라진 문서"],
                             "page_ids": ["wikipedia_ko-1", "wikipedia_en-9"]}}
    assert docs_store.migrate_filenames(manifest) == 1
    assert not legacy.exists() and docs_store.doc_path("ethereum", "wikipedia_ko-1").exists()
    assert manifest["ethereum"] == {"keywords": ["item:ko:이더리움"], "titles": ["이더리움"],
                                    "page_ids": ["wikipedia_ko-1"]}



# --- Codex 요구사항 점검(2026-10-22 15:33) 회귀 테스트 ---

def test_no_contact_skips_wiki_calls(env, monkeypatch):
    from src.config import user_agent

    monkeypatch.delenv("CONTACT_EMAIL")
    assert "contact" not in user_agent() and "set CONTACT_EMAIL" not in user_agent()
    with pytest.raises(collect.wiki.MissingContactError):
        collect.wiki.make_client()
    monkeypatch.setattr(collect, "_wiki_client", None)
    script('["지분증명"]', "[1]")
    out = collect.collect("ethereum", "지분증명 전환")
    assert out["added_titles"] == [] and "CONTACT_EMAIL" in out["notice"]
    assert env["search"] == [] and env["fetch"] == []


def test_user_agent_has_contact(monkeypatch):
    from src.config import user_agent

    monkeypatch.setenv("CONTACT_EMAIL", "me@example.com")
    assert "contact: me@example.com" in user_agent()
    monkeypatch.setenv("CONTACT_EMAIL", "not-a-contact")
    assert "not-a-contact" not in user_agent()


def test_is_item_page_rules():
    rain = {"name": "Rain", "name_ko": "", "symbol": "RAIN"}
    assert collect.wiki.is_item_page(rain, {"title": "Rain (cryptocurrency)", "snippet": ""})
    assert collect.wiki.is_item_page(rain, {"title": "RAIN", "snippet": "Arbitrum options protocol token"})
    assert not collect.wiki.is_item_page(rain, {"title": "레인 (가수)", "snippet": "대한민국의 가수"})
    assert not collect.wiki.is_item_page(rain, {"title": "Rain", "snippet": "Rain is liquid water"})
    assert not collect.wiki.is_item_page(rain, {"title": "Rain Bahrain exchange", "snippet": "crypto exchange"})


def test_unlinked_coin_item_doc_found_by_search_bypasses_selection(env, monkeypatch):
    def search(_c, q, lang="ko", limit=5):
        env["search"].append(q)
        return [{"page_id": 77, "title": "Rain (cryptocurrency)", "snippet": "options protocol", "size": 1, "lang": lang},
                {"page_id": 11, "title": "레인 (가수)", "snippet": "대한민국의 가수", "size": 1, "lang": lang}]

    def fetch(_c, title, lang="ko"):
        env["fetch"].append(title)
        return {**page(title, lang, 77), "text": "짧은 문서"}            # 최소 길이(300자) 미만

    monkeypatch.setattr(collect.wiki, "search", search)
    monkeypatch.setattr(collect.wiki, "fetch_page", fetch)
    script('["옵션"]', "[]")                                          # 선별 프롬프트는 아무것도 고르지 않음
    out = collect.collect("rain", "옵션 프로토콜 구조는?")
    assert out["added_titles"] == ["Rain (cryptocurrency)"]
    doc = next(d for d in docs_store.iter_docs() if d["coin_id"] == "rain")
    assert doc["is_item_doc"] is True and doc["search_query"].startswith("item:search:")
    assert "item:search" in docs_store.load_manifest()["rain"]["keywords"]

    n = len(env["search"])
    script('["옵션"]', "[]")
    collect.collect("rain", "옵션 프로토콜 구조는?")                     # 다시 물어도 자체 문서 검색은 반복하지 않음
    assert sum("암호화폐" in q or "cryptocurrency" in q for q in env["search"][n:]) == 0


def test_recommend_candidates_include_condition_attributes(env, monkeypatch):
    from src.data_prep import items
    from src.service import recommend

    btc = {"coin_id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "name_ko": "비트코인", "market_cap_rank": 1,
           "categories": ["Layer 1 (L1)"], "hashing_algorithm": "SHA-256", "genesis_date": "2009-01-03",
           "asset_platform_id": None, "description_ko": "", "description_en": "Peer-to-peer cash"}
    line = items.candidate_line(btc)
    for part in ("1위", "Layer 1 (L1)", "SHA-256", "2009-01-03", "Peer-to-peer"):
        assert part in line

    class Doc:
        metadata = {"coin_id": "ethereum"}

    class Col:
        def similarity_search(self, q, k):
            return [Doc()]

    seen = {}
    monkeypatch.setattr(recommend.store, "collection", lambda key: Col())
    monkeypatch.setattr(recommend.llm, "ask", lambda system, user: seen.setdefault("user", user) and '[{"n": 1, "reason": "L1"}]')
    out = recommend.recommend("시가총액 2위 레이어1")
    assert "시가총액 순위 2위" in seen["user"] and "Layer 1 (L1)" in seen["user"]
    assert out[0]["coin_id"] == "ethereum"


def test_unlinked_coin_falls_back_to_whitepaper_with_page_citation(env, monkeypatch):
    from src.data_prep import whitepaper

    catalog.get("rain")["whitepaper"] = "https://rain.one/whitepaper.pdf"
    calls = []

    def fetch(client, coin, url):
        calls.append(url)
        return {"page_id": "wp1", "title": "Rain 백서", "url": url, "text": "x", "source": "백서 PDF",
                "source_type": "whitepaper_pdf", "license": "저작권: 각 프로젝트", "file_name": "whitepaper.pdf",
                "pages": [{"page": 1, "text": "Rain 은 Arbitrum 위의 옵션 프로토콜이다. " * 5},
                          {"page": 7, "text": "RAIN 토큰은 수수료로 소각된다. " * 5}]}

    monkeypatch.setattr(whitepaper, "fetch", fetch)
    monkeypatch.setattr(collect, "_wp_client", object())
    script('["옵션"]', "[]")
    out = collect.collect("rain", "토큰 소각 구조는?")                     # 위키 검색은 일치 없음 → 백서
    assert out["added_titles"] == ["Rain 백서"] and calls == ["https://rain.one/whitepaper.pdf"]
    assert "wp:https://rain.one/whitepaper.pdf" in docs_store.load_manifest()["rain"]["keywords"]

    script('["옵션"]', "[]")
    collect.collect("rain", "토큰 소각 구조는?")
    assert calls == ["https://rain.one/whitepaper.pdf"]                    # 같은 백서는 다시 받지 않음

    script("RAIN 은 수수료로 소각됩니다 [근거 2].")
    ans = graph.run("rain", "토큰 소각 구조는?")
    src = ans["sources"][0]
    assert src["source_type"] == "whitepaper_pdf" and src["source_label"] == "백서 PDF" and src["page"] in (1, 7)
