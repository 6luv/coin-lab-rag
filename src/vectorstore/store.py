"""Vector Store 영역: 컬렉션 생성·조회, 청킹, 색인 (F2002, F2005).

- coin_meta: 코인 1건 = 청크 1개, id = coin_id  → 다시 색인해도 덮어쓰기만 일어난다.
- coin_docs: 외부 문서 청크, id = "{coin_id}:{doc_id}:{순번}" → 여러 코인이 같은 문서를 모아도 충돌하지 않는다.
- 청크 크기·중복 길이는 config/settings.json (또는 CHUNK_SIZE/CHUNK_OVERLAP 환경변수) 에서만 바꾼다.
"""
from __future__ import annotations

from src.config import embedding_model, embedding_provider, gms_key, openai_base_url, path, settings


class MissingKeyError(RuntimeError):
    pass


def embeddings():
    if embedding_provider() == "fake":
        # API 키 없이 색인 흐름(건수·중복·청크 ID)만 검증할 때 사용. 검색 품질은 의미 없다.
        from langchain_core.embeddings import DeterministicFakeEmbedding

        return DeterministicFakeEmbedding(size=256)
    key = gms_key()
    if not key:
        raise MissingKeyError("GMS_KEY(또는 OPENAI_API_KEY)가 설정되지 않았습니다. .env 를 확인하세요.")
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=embedding_model(), api_key=key, base_url=openai_base_url())


def collection(name_key: str):
    from langchain_chroma import Chroma

    suffix = "_fake" if embedding_provider() == "fake" else ""  # 차원이 다른 임베딩이 섞이지 않게
    return Chroma(
        collection_name=settings()["collections"][name_key] + suffix,
        embedding_function=embeddings(),
        persist_directory=str(path("chroma_dir")),
    )


def count(name_key: str) -> int:
    try:
        return collection(name_key)._collection.count()
    except MissingKeyError:
        raise
    except Exception:
        return 0


def splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    c = settings()["chunk"]
    return RecursiveCharacterTextSplitter(
        chunk_size=c["size"], chunk_overlap=c["overlap"], separators=["\n\n", "\n", ". ", "다. ", " ", ""]
    )


def chunk_doc(doc: dict) -> list[tuple[str, str, dict]]:
    """문서 1건 → [(chunk_id, text, metadata)]"""
    parts = splitter().split_text(doc["text"])
    out = []
    for i, text in enumerate(parts):
        meta = {
            "coin_id": doc["coin_id"],
            "related_coin": doc["related_coin"],
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "url": doc["url"],
            "source": doc["source"],
            "source_type": doc["source_type"],
            "source_label": doc["source"],
            "search_query": doc.get("search_query", ""),
            "is_item_doc": bool(doc.get("is_item_doc")),
            "collected_at": doc.get("collected_at", ""),
            "chunk_index": i,
        }
        out.append((f"{doc['coin_id']}:{doc['doc_id']}:{i}", text, meta))
    return out


def raw_count(name_key: str) -> int:
    """임베딩 없이 Chroma 에 바로 물어 건수를 센다 (키가 없어도 상태 표시 가능)."""
    import chromadb

    suffix = "_fake" if embedding_provider() == "fake" else ""
    d = path("chroma_dir")
    if not d.exists():
        return 0
    try:
        client = chromadb.PersistentClient(path=str(d))
        return client.get_collection(settings()["collections"][name_key] + suffix).count()
    except Exception:
        return 0


def index_doc(col, doc: dict) -> int:
    """문서 1건을 청킹해 coin_docs 에 넣는다.

    새 청크를 먼저 넣고(같은 ID 는 덮어쓰기) 그다음 새 목록에 없는 이전 청크만 지운다.
    임베딩 호출이 실패하면 이전 색인이 그대로 남는다.
    """
    chunks = chunk_doc(doc)
    old = col._collection.get(where={"$and": [{"coin_id": doc["coin_id"]}, {"doc_id": doc["doc_id"]}]}, include=[])["ids"]
    ids: list[str] = []
    if chunks:
        ids, texts, metas = (list(x) for x in zip(*chunks))
        col.add_texts(texts=texts, metadatas=metas, ids=ids)
    stale = sorted(set(old) - set(ids))
    if stale:
        col._collection.delete(ids=stale)
    return len(chunks)


def is_doc_indexed(col, coin_id: str, doc_id: str) -> bool:
    got = col._collection.get(where={"$and": [{"coin_id": coin_id}, {"doc_id": doc_id}]}, limit=1, include=[])
    return bool(got["ids"])
