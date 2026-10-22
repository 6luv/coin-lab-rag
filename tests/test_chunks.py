"""청크 식별자·설정 반영 확인 (langchain-text-splitters 필요)."""
import pytest

pytest.importorskip("langchain_text_splitters")

from src.config import settings  # noqa: E402
from src.vectorstore import store  # noqa: E402

DOC = {
    "coin_id": "ethereum", "related_coin": "Ethereum", "doc_id": "wikipedia_ko-123",
    "title": "이더리움", "url": "https://ko.wikipedia.org/wiki/x", "source": "한국어 위키백과",
    "source_type": "wikipedia_ko", "text": "가나다라마바사. " * 400, "is_item_doc": True,
}


def test_chunk_ids_unique_and_scoped():
    chunks = store.chunk_doc(DOC)
    ids = [c[0] for c in chunks]
    assert len(ids) == len(set(ids)) > 1
    assert ids[0] == "ethereum:wikipedia_ko-123:0"
    other = store.chunk_doc({**DOC, "coin_id": "bitcoin"})
    assert not set(ids) & {c[0] for c in other}  # 같은 문서를 다른 코인이 모아도 충돌 없음


def test_chunk_size_from_settings(monkeypatch):
    base = len(store.chunk_doc(DOC))
    monkeypatch.setitem(settings()["chunk"], "size", 300)
    monkeypatch.setitem(settings()["chunk"], "overlap", 50)
    assert len(store.chunk_doc(DOC)) > base
    assert all(len(t) <= 300 for _, t, _ in store.chunk_doc(DOC))
