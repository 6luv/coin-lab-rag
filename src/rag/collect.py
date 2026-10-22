"""질문 기반 외부 문서 수집 (F2003 · F2004 · F2005 · NF2002).

1. 코인 자체 문서(위키데이터 연결)는 선별·길이 규칙보다 우선해 항상 수집·색인한다.
2. 프롬프트1로 검색어를 뽑고, 이미 검색한 검색어는 건너뛴다 (manifest).
3. 위키백과 후보(제목·요약)만 모아 프롬프트2로 고른 문서만 본문을 받는다.
4. 받은 문서는 바로 청킹해 coin_docs 에 색인한다.
5. 검색어는 그 검색어로 고른 문서의 수집·색인이 모두 성공했을 때만 '완료'로 기록한다 (실패하면 다음 질문 때 다시 시도).
6. 저장은 됐지만 색인되지 않은 문서(임베딩 실패 등)는 다음 수집 때 저장 파일로 다시 색인한다.
"""
from __future__ import annotations

import json
import logging
import threading

import requests

from src.config import contact, settings
from src.data_prep import catalog, docs_store, prompts, whitepaper, wiki
from src.rag import llm
from src.vectorstore import store
from src.vectorstore.store import MissingKeyError

log = logging.getLogger("coinlab.collect")
NETWORK_ERRORS = (RuntimeError, requests.RequestException, ValueError)
_lock = threading.Lock()  # 같은 파일·색인을 동시에 고치지 않도록 한 번에 하나만 수집한다
_wiki_client = None


def _client():
    global _wiki_client
    if _wiki_client is None:
        _wiki_client = wiki.make_client()
    return _wiki_client


def extract_keywords(coin: dict, question: str) -> list[str]:
    """프롬프트1. 파싱에 실패하면 질문 원문을 검색어로 쓴다."""
    cfg = settings()["collect"]
    raw = llm.ask(
        prompts.KEYWORDS_SYSTEM.format(max_keywords=cfg["max_keywords"]),
        prompts.KEYWORDS_USER.format(
            label=coin["label"], categories=", ".join(coin.get("categories") or []) or "-", question=question
        ),
    )
    words = llm.parse_json(raw, list)
    if words is None:  # 파싱 실패: 코인 이름 + 질문 앞부분
        words = [f"{coin['name']} {question[:30]}"]
    seen, out = set(), []
    for w in words:
        w = str(w).strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[: cfg["max_keywords"]]


def select_candidates(coin: dict, question: str, candidates: list[dict]) -> list[dict]:
    """프롬프트2. 번호 배열을 받아 후보를 고른다.

    정상 응답 `[]` 은 '고를 문서 없음'(검색어 완료), 파싱 실패는 ValueError(검색어 미완료 → 다음에 재시도).
    """
    if not candidates:
        return []
    cfg = settings()["collect"]
    listing = "\n".join(
        f"{i}. [{c['lang']}] {c['title']} — {c['snippet'][:160]}" for i, c in enumerate(candidates, 1)
    )
    raw = llm.ask(
        prompts.SELECT_SYSTEM.format(max_docs=cfg["max_new_docs"]),
        prompts.SELECT_USER.format(label=coin["label"], question=question, candidates=listing),
    )
    picked = llm.parse_json(raw, list)
    if picked is None:
        raise ValueError("후보 선별 응답을 JSON 배열로 읽지 못함")
    out = []
    for n in picked:
        if isinstance(n, int) and 1 <= n <= len(candidates) and candidates[n - 1] not in out:
            out.append(candidates[n - 1])
    return out[: cfg["max_new_docs"]]


def _save_and_index(col, page: dict, coin: dict, keyword: str, manifest: dict, is_item_doc: bool) -> dict:
    out = docs_store.save_doc(page, coin, keyword, manifest, is_item_doc=is_item_doc)
    record = json.loads(out.read_text(encoding="utf-8"))
    store.index_doc(col, record)
    return record


def _reindex_saved(col, coin_id: str, report: dict) -> list[dict]:
    """저장 파일은 있는데 색인에 없는 문서를 다시 색인한다 (색인 스크립트 미실행, 임베딩 실패·제공자 변경)."""
    saved = [d for d in docs_store.iter_docs() if d.get("coin_id") == coin_id]
    for d in saved:
        if store.is_doc_indexed(col, coin_id, d["doc_id"]):
            continue
        try:
            store.index_doc(col, d)
        except MissingKeyError:
            raise
        except Exception as e:
            log.warning("재색인 실패 (%s %s): %s", coin_id, d["doc_id"], type(e).__name__)
            report["errors"] += 1
    return saved


def _ensure_item_doc(col, coin: dict, manifest: dict, report: dict, saved: list[dict]) -> list[str]:
    """코인 자체 문서를 항상 수집·색인 상태로 만든다 (F2004 우선 규칙).

    한국어 문서가 없거나 받지 못하면 영어 문서를 시도한다.
    """
    coin_id = coin["coin_id"]
    if any(d.get("is_item_doc") for d in saved):
        return []
    added = []
    for lang, title in (("ko", coin.get("kowiki_title")), ("en", coin.get("enwiki_title"))):
        if not title:
            continue
        keyword = f"item:{lang}:{title}"
        if docs_store.already_collected(manifest, coin_id, keyword):
            continue  # 이전에 '문서 없음'으로 확인된 제목
        try:
            page = wiki.fetch_page(_client(), title, lang)
        except NETWORK_ERRORS:
            report["errors"] += 1
            continue  # 기록하지 않아 다음 요청 때 다시 시도
        if page:
            try:
                added.append(_save_and_index(col, page, coin, keyword, manifest, is_item_doc=True)["title"])
            except MissingKeyError:
                raise
            except Exception as e:  # 파일은 저장됐을 수 있다 → 다음 수집 때 _reindex_saved 가 다시 색인
                log.warning("자체 문서 색인 실패 (%s): %s", coin_id, type(e).__name__)
                report["errors"] += 1
            break
        docs_store.mark_keyword(manifest, coin_id, keyword)
    if not added and not (coin.get("kowiki_title") or coin.get("enwiki_title")):
        added += _search_item_doc(col, coin, manifest, report)
    return added


def _search_item_doc(col, coin: dict, manifest: dict, report: dict) -> list[str]:
    """위키데이터 연결이 없는 코인: 검색으로 자체 문서를 찾아 선별·길이 규칙 없이 색인한다 (F2004, D12).
    위키에 없으면 백서를 자체 문서로 쓴다 (D14).

    한 번 찾아봤으면(찾았든 없든) 'item:search' 로 기록해 다시 검색하지 않는다. 네트워크·색인 실패는 기록하지 않는다.
    """
    coin_id = coin["coin_id"]
    if docs_store.already_collected(manifest, coin_id, "item:search"):
        return _whitepaper_item_doc(col, coin, manifest, report)
    try:
        page = wiki.find_item_page(_client(), coin)
    except NETWORK_ERRORS:
        report["errors"] += 1
        return []
    if not page:  # 위키에 없으면 백서로
        docs_store.mark_keyword(manifest, coin_id, "item:search")
        return _whitepaper_item_doc(col, coin, manifest, report)
    keyword = f"item:search:{page['source_type']}:{page['title']}"
    try:
        title = _save_and_index(col, page, coin, keyword, manifest, is_item_doc=True)["title"]
    except MissingKeyError:
        raise
    except Exception as e:
        log.warning("자체 문서 색인 실패 (%s): %s", coin_id, type(e).__name__)
        report["errors"] += 1
        return []
    docs_store.mark_keyword(manifest, coin_id, "item:search")
    return [title]


_wp_client = None


def _whitepaper_item_doc(col, coin: dict, manifest: dict, report: dict) -> list[str]:
    """위키 자체 문서가 없는 코인: 백서(PDF·웹)를 자체 문서로 수집·색인한다 (F2004 · F2016). 한 URL 은 한 번만 시도."""
    global _wp_client
    url = coin.get("whitepaper")
    key = f"wp:{url}"
    if not url or docs_store.already_collected(manifest, coin["coin_id"], key):
        return []
    if _wp_client is None:
        _wp_client = whitepaper.make_client()
    try:
        doc = whitepaper.fetch(_wp_client, coin, url)
    except NETWORK_ERRORS:
        report["errors"] += 1
        return []
    added = []
    if doc:
        try:
            added.append(_save_and_index(col, doc, coin, key, manifest, is_item_doc=True)["title"])
        except MissingKeyError:
            raise
        except Exception as e:
            log.warning("백서 색인 실패 (%s): %s", coin["coin_id"], type(e).__name__)
            report["errors"] += 1
            return []
    docs_store.mark_keyword(manifest, coin["coin_id"], key)
    return added


def _search_keywords(coin: dict, question: str) -> list[str]:
    words = extract_keywords(coin, question)
    if not (coin.get("kowiki_title") or coin.get("enwiki_title")):
        # 연결된 위키 문서가 없는 코인은 코인 이름 검색어를 맨 앞에 둔다 (오검색은 프롬프트2가 거른다)
        words = [f"{coin['name']} 암호화폐", *words]
    return words[: settings()["collect"]["max_keywords"] + 1]


def collect(coin_id: str, question: str) -> dict:
    coin = catalog.get(coin_id)
    if coin is None:
        raise KeyError(coin_id)
    cfg = settings()["collect"]
    report = {"keywords": [], "skipped_keywords": [], "candidates": [], "selected": [], "errors": 0}
    with _lock:
        col = store.collection("docs")
        manifest = docs_store.load_manifest()
        added: list[str] = []
        try:
            saved = _reindex_saved(col, coin_id, report)
            if not contact():  # NF2006: 연락처 없이 위키 API 를 부르지 않는다. 저장된 문서로만 답한다
                report["notice"] = wiki.CONTACT_MISSING
            else:
                added += _ensure_item_doc(col, coin, manifest, report, saved)
                if question.strip():
                    added += _collect_for_question(col, coin, question, manifest, report, cfg)
        finally:
            docs_store.save_manifest(manifest)  # 중간에 실패해도 이미 저장·색인한 문서 기록은 남긴다
        titles = manifest.get(coin_id, {}).get("titles", [])
    return {"added_titles": added, "titles": titles, **report}


def _collect_for_question(col, coin: dict, question: str, manifest: dict, report: dict, cfg: dict) -> list[str]:
    coin_id = coin["coin_id"]
    try:
        keywords = _search_keywords(coin, question)
    except MissingKeyError:
        raise
    except Exception as e:  # LLM 호출 실패: 수집만 건너뛰고 답변은 기존 문서로 진행
        log.warning("검색어 추출 실패 (%s): %s", coin_id, type(e).__name__)
        report["errors"] += 1
        return []
    known = set(manifest.get(coin_id, {}).get("page_ids", []))
    candidates, seen, searched = [], set(), []
    for kw in keywords:
        key = f"q:{kw.lower()}"
        if docs_store.already_collected(manifest, coin_id, key):
            report["skipped_keywords"].append(kw)
            continue
        try:
            rows = wiki.search(_client(), kw, "ko", cfg["candidates_per_keyword"])
            if len(rows) < 2:
                rows += wiki.search(_client(), kw, "en", cfg["candidates_per_keyword"])
        except NETWORK_ERRORS:
            report["errors"] += 1
            continue  # 기록하지 않아 다음 질문 때 다시 검색
        report["keywords"].append(kw)
        searched.append(kw)
        for r in rows:
            ident = (r["lang"], r["page_id"])
            if ident in seen or f"wikipedia_{r['lang']}-{r['page_id']}" in known:
                continue
            seen.add(ident)
            candidates.append({**r, "keyword": kw})
    report["candidates"] = [c["title"] for c in candidates]
    try:
        chosen = select_candidates(coin, question, candidates)
    except MissingKeyError:
        raise
    except Exception as e:
        log.warning("후보 선별 실패 (%s): %s", coin_id, type(e).__name__)
        report["errors"] += 1
        return []  # 검색어를 기록하지 않아 다음에 다시 선별
    added, failed = [], set()
    for c in chosen:
        try:
            page = wiki.fetch_page(_client(), c["title"], c["lang"])
        except NETWORK_ERRORS:
            report["errors"] += 1
            failed.add(c["keyword"])
            continue
        if not page or len(page["text"]) < cfg["min_doc_chars"]:
            continue
        try:
            title = _save_and_index(col, page, coin, f"q:{c['keyword'].lower()}", manifest, False)["title"]
        except MissingKeyError:
            raise
        except Exception as e:  # 색인 실패: 저장 파일은 다음 수집 때 _reindex_saved 가 복구
            log.warning("문서 색인 실패 (%s %s): %s", coin_id, page["title"], type(e).__name__)
            report["errors"] += 1
            failed.add(c["keyword"])
            continue
        report["selected"].append(title)
        added.append(title)
    # 본문 수집·색인이 하나라도 실패한 검색어는 기록하지 않아 다음 질문 때 다시 시도한다 (NF2002)
    for kw in searched:
        if kw not in failed:
            docs_store.mark_keyword(manifest, coin_id, f"q:{kw.lower()}")
    return added
