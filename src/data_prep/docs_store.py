"""수집한 외부 문서 저장소 (파일 + manifest).

파일: data/docs/{종류}/{coin_id}_{doc_id}.json  (doc_id = "wikipedia_ko-123", "whitepaper_pdf-…": 종류·언어가 달라도 겹치지 않는다)
종류: wikipedia(위키백과, CC BY-SA — git 포함), whitepaper(백서 PDF·웹, 저작권은 각 프로젝트 — git 제외)
manifest: 코인별로 이미 검색한 키워드·수집한 문서를 기록해 재수집을 막는다. (NF2002)
검색어 완료 기록(mark_keyword)은 문서 저장과 분리해, 수집·색인이 모두 성공했을 때만 호출한다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from src.config import path

_UNSAFE = re.compile(r'[\\/:*?"<>|\s()]+')


KINDS = ("wikipedia", "whitepaper")


def kind_of(source_type: str) -> str:
    return "whitepaper" if (source_type or "").startswith("whitepaper") else "wikipedia"


def docs_dir(kind: str = "wikipedia") -> Path:
    d = path("docs_dir") / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(title: str) -> str:
    return _UNSAFE.sub("_", title).strip("_")[:80]


def load_manifest() -> dict:
    p = path("manifest")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict) -> None:
    p = path("manifest")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def already_collected(manifest: dict, coin_id: str, keyword: str) -> bool:
    return keyword in manifest.get(coin_id, {}).get("keywords", [])


def doc_path(coin_id: str, doc_id: str, kind: str | None = None) -> Path:
    return docs_dir(kind or kind_of(doc_id)) / f"{coin_id}_{safe_name(doc_id)}.json"


def _entry(manifest: dict, coin_id: str) -> dict:
    return manifest.setdefault(coin_id, {"keywords": [], "titles": [], "page_ids": []})


def save_doc(doc: dict, coin: dict, keyword: str, manifest: dict, is_item_doc: bool) -> Path:
    """문서 파일을 쓰고 manifest 에 문서를 기록한다. 검색어 완료 기록은 하지 않는다."""
    record = {
        "page_id": doc["page_id"],
        "doc_id": f"{doc['source_type']}-{doc['page_id']}",
        "title": doc["title"],
        "url": doc["url"],
        "text": doc["text"],
        "source": doc["source"],
        "source_type": doc["source_type"],
        "license": doc.get("license", ""),
        "coin_id": coin["coin_id"],
        "related_coin": coin["name"],
        "search_query": keyword,
        "is_item_doc": is_item_doc,
        "lastrevid": doc.get("lastrevid"),
        "collected_at": date.today().isoformat(),
    }
    if doc.get("pages"):  # PDF: 쪽 단위 텍스트와 파일명 (근거에 쪽 번호를 붙인다)
        record["pages"] = doc["pages"]
        record["file_name"] = doc.get("file_name", "")
    out = doc_path(coin["coin_id"], record["doc_id"])
    out.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    entry = _entry(manifest, coin["coin_id"])
    if record["doc_id"] not in entry["page_ids"]:
        entry["page_ids"].append(record["doc_id"])
    if doc["title"] not in entry["titles"]:
        entry["titles"].append(doc["title"])
    return out


def mark_keyword(manifest: dict, coin_id: str, keyword: str) -> None:
    entry = _entry(manifest, coin_id)
    if keyword not in entry["keywords"]:
        entry["keywords"].append(keyword)


def iter_docs(kind: str | None = None):
    """(coin_id, doc_id) 당 한 건. kind 를 주지 않으면 모든 종류. 이름 규칙이 같은 새 파일을 우선한다."""
    picked: dict[tuple, tuple[bool, dict]] = {}
    files = [f for k in ([kind] if kind else KINDS) for f in sorted(docs_dir(k).glob("*.json"))]
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        key = (d.get("coin_id"), d.get("doc_id"))
        is_new_name = f == doc_path(*key) if all(key) else False
        if key not in picked or (is_new_name and not picked[key][0]):
            picked[key] = (is_new_name, d)
    for _, d in picked.values():
        yield d


def migrate_filenames(manifest: dict, kind: str = "wikipedia") -> int:
    """이전 이름 규칙({coin_id}_{제목}.json) 파일을 새 이름으로 옮기고 manifest 문서 목록을 실제 파일에 맞춘다.

    새 이름 파일이 이미 있으면 이전 파일은 그대로 두고(iter_docs 가 새 파일을 쓴다) 건드리지 않는다.
    """
    moved = 0
    for f in sorted(docs_dir(kind).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not (d.get("coin_id") and d.get("doc_id")):
            continue
        target = doc_path(d["coin_id"], d["doc_id"])
        if f != target and not target.exists():
            f.rename(target)
            moved += 1
    files: dict[str, list[dict]] = {}
    for d in iter_docs():  # manifest 문서 목록은 모든 종류 기준
        files.setdefault(d["coin_id"], []).append(d)
    for coin_id, entry in manifest.items():
        docs = files.get(coin_id, [])
        entry["page_ids"] = [d["doc_id"] for d in docs]
        entry["titles"] = list(dict.fromkeys(d["title"] for d in docs))
    for coin_id, docs in files.items():
        if coin_id not in manifest:
            entry = _entry(manifest, coin_id)
            entry["page_ids"] = [d["doc_id"] for d in docs]
            entry["titles"] = list(dict.fromkeys(d["title"] for d in docs))
    return moved
