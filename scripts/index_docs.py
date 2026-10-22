"""F2005: 수집한 외부 문서를 청킹해 coin_docs 컬렉션에 색인.

  python -m scripts.index_docs
  CHUNK_SIZE=500 CHUNK_OVERLAP=100 python -m scripts.index_docs --rebuild   # 설정 비교
"""
from __future__ import annotations

import argparse

from src.config import settings
from src.data_prep import docs_store
from src.vectorstore import store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="컬렉션을 비우고 다시 색인 (청크 설정 변경 시)")
    args = ap.parse_args()
    if store.server_running():
        print(store.SERVER_BUSY)
        return 2

    col = store.collection("docs")
    if args.rebuild:
        col.reset_collection()
    n_docs = n_chunks = 0
    manifest = docs_store.load_manifest()
    moved = docs_store.migrate_filenames(manifest)  # 이전 이름 규칙 파일 정리 + manifest 문서 목록 맞춤
    docs_store.save_manifest(manifest)
    if moved:
        print(f"문서 파일 {moved}개를 새 이름 규칙({{coin_id}}_{{doc_id}}.json)으로 옮김")
    docs = list(docs_store.iter_docs())
    # 문서 파일이 지워진 (코인, 문서) 조합의 청크는 색인에서도 지운다
    present = {(d["coin_id"], d["doc_id"]) for d in docs}
    got = col._collection.get(include=["metadatas"])
    if not docs and got["ids"]:
        print("문서 파일이 0건이라 기존 색인 정리를 건너뜁니다. (전체 재색인은 --rebuild)")
        got = {"ids": [], "metadatas": []}
    orphan = [i for i, m in zip(got["ids"], got["metadatas"]) if (m.get("coin_id"), m.get("doc_id")) not in present]
    if orphan:
        col._collection.delete(ids=orphan)
        print(f"원본 문서가 없는 청크 {len(orphan)}개 삭제")
    for doc in docs:
        added = store.index_doc(col, doc)
        if added:
            n_docs += 1
            n_chunks += added
    c = settings()["chunk"]
    print(f"문서 {n_docs}건 → 청크 {n_chunks}개 (size={c['size']}, overlap={c['overlap']}) · coin_docs 총 {col._collection.count()}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
