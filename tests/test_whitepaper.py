"""F2016 백서 수집: 가짜 HTTP 응답으로 PDF·웹 문서 처리, 쪽 단위 청킹, 질문 시 대체 수집을 확인한다 (네트워크 없음)."""
from src.data_prep import docs_store, whitepaper
from src.vectorstore import store

COIN = {"coin_id": "ethena", "name": "Ethena", "symbol": "ENA", "name_ko": ""}
PARA = "Ethena is a synthetic dollar protocol built on Ethereum that provides a crypto-native solution for money. "


def make_pdf(pages: list[str]) -> bytes:
    """외부 라이브러리 없이 글자가 든 최소 PDF 를 만든다 (쪽마다 한 줄씩 90자)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        lines = [text[i:i + 90].replace("\\", "").replace("(", "").replace(")", "") for i in range(0, len(text), 90)]
        ops = "BT /F1 9 Tf 14 TL 40 800 Td " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
        objs.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")
        content = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content} 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class Resp:
    def __init__(self, body: bytes, ctype: str, url: str):
        self.content, self.headers, self.url = body, {"Content-Type": ctype}, url
        self.text = body.decode("utf-8", "replace")


class Client:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def get(self, url, params=None, max_bytes=None):
        self.calls.append(url)
        return self.resp


def test_html_to_text_skips_scripts_and_menus():
    title, text = whitepaper.html_to_text(
        "<html><head><title>Ethena Docs</title><script>var x=1</script></head>"
        "<body><nav>Home | Docs</nav><h1>Overview</h1><p>USDe is a synthetic dollar.</p><footer>©</footer></body></html>")
    assert title == "Ethena Docs"
    assert "USDe is a synthetic dollar." in text and "Overview" in text
    assert "var x" not in text and "Home | Docs" not in text and "©" not in text


def test_fetch_pdf_keeps_pages_and_file_name():
    body = make_pdf([PARA * 4, PARA * 5])
    doc = whitepaper.fetch(Client(Resp(body, "application/pdf", "https://ethena.fi/files/whitepaper.pdf")), COIN,
                           "https://ethena.fi/files/whitepaper.pdf")
    assert doc["source_type"] == "whitepaper_pdf" and doc["source"] == "백서 PDF"
    assert [p["page"] for p in doc["pages"]] == [1, 2] and doc["file_name"] == "whitepaper.pdf"
    assert "synthetic dollar" in doc["text"] and doc["license"].startswith("저작권")


def test_fetch_rejects_short_or_unsupported():
    short = Client(Resp(b"<html><body><div id=app></div></body></html>", "text/html", "https://x.io"))
    assert whitepaper.fetch(short, COIN, "https://x.io") is None              # 스크립트로 그리는 페이지
    assert whitepaper.fetch(Client(Resp(b"\x89PNG", "image/png", "https://x.io/a.png")), COIN, "https://x.io/a.png") is None
    assert whitepaper.fetch(Client(None), COIN, "ftp://x.io/a.pdf") is None    # http(s) 만


def test_pdf_chunks_do_not_cross_pages_and_store_page(tmp_path, monkeypatch):
    from src.config import settings

    monkeypatch.setitem(settings()["paths"], "docs_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(settings()["paths"], "manifest", str(tmp_path / "docs/manifest.json"))
    doc = {"page_id": "abc", "title": "Ethena 백서", "url": "https://ethena.fi/w.pdf", "text": "x",
           "pages": [{"page": 1, "text": PARA * 15}, {"page": 2, "text": PARA * 3}],
           "file_name": "w.pdf", "source": "백서 PDF", "source_type": "whitepaper_pdf", "license": "저작권"}
    manifest = {}
    out = docs_store.save_doc(doc, COIN, "wp:https://ethena.fi/w.pdf", manifest, is_item_doc=True)
    assert out.parent.name == "whitepaper" and out.name == "ethena_whitepaper_pdf-abc.json"
    saved = next(docs_store.iter_docs())
    chunks = store.chunk_doc(saved)
    pages = [m["page"] for _, _, m in chunks]
    assert pages == sorted(pages) and set(pages) == {1, 2} and len(chunks) >= 3
    assert all(m["file_name"] == "w.pdf" for _, _, m in chunks)
    assert [cid for cid, _, _ in chunks][0] == "ethena:whitepaper_pdf-abc:0"
    assert manifest["ethena"]["page_ids"] == ["whitepaper_pdf-abc"]


def test_wiki_docs_have_no_page_metadata():
    doc = {"coin_id": "ethena", "related_coin": "Ethena", "doc_id": "wikipedia_en-1", "title": "Ethena",
           "url": "u", "source": "English Wikipedia", "source_type": "wikipedia_en", "text": PARA * 3}
    assert all("page" not in m for _, _, m in store.chunk_doc(doc))


# --- Codex 점검(2026-10-22 16:25): GitHub 미리보기 화면을 백서로 받던 문제 ---
GITHUB_CHROME = ("<html><body><a>Skip to content</a><p>You signed in with another tab or window. Reload to refresh "
                 "your session.</p><p>Download raw file</p><p>Loading Viewer requires iframe.</p>" + "<p>menu</p>" * 200
                 + "</body></html>").encode()


def test_resolve_github_links():
    blob = "https://github.com/aave/gho-core/blob/main/techpaper/GHO_Technical_Paper.pdf"
    assert whitepaper.resolve_url(blob) == "https://raw.githubusercontent.com/aave/gho-core/main/techpaper/GHO_Technical_Paper.pdf"
    assert whitepaper.resolve_url("https://github.com/pendle-finance/pendle-v2-resources/tree/main/whitepapers") is None
    assert whitepaper.resolve_url("https://docs.ethena.fi/") == "https://docs.ethena.fi/"


def test_github_blob_fetches_raw_pdf():
    client = Client(Resp(make_pdf([PARA * 6]), "application/octet-stream", "https://raw.githubusercontent.com/a/b/main/w.pdf"))
    doc = whitepaper.fetch(client, COIN, "https://github.com/a/b/blob/main/w.pdf")
    assert client.calls == ["https://raw.githubusercontent.com/a/b/main/w.pdf"]
    assert doc["source_type"] == "whitepaper_pdf" and doc["url"] == "https://github.com/a/b/blob/main/w.pdf"


def test_viewer_page_is_not_a_whitepaper():
    client = Client(Resp(GITHUB_CHROME, "text/html", "https://example.com/viewer"))
    assert whitepaper.fetch(client, COIN, "https://example.com/viewer") is None


def test_prune_removes_bad_saved_docs(tmp_path, monkeypatch):
    import json

    from scripts import collect_whitepapers
    from src.config import settings

    monkeypatch.setitem(settings()["paths"], "docs_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(settings()["paths"], "manifest", str(tmp_path / "docs/manifest.json"))
    manifest = {}
    bad_url = "https://github.com/aave/gho-core/blob/main/techpaper/GHO_Technical_Paper.pdf"
    good = {"page_id": "g", "title": "Ethena 백서", "url": "https://docs.ethena.fi/", "text": PARA * 10,
            "source": "백서(웹)", "source_type": "whitepaper_web", "license": "저작권"}
    bad = {**good, "page_id": "b", "title": "GHO 백서", "url": bad_url,
           "text": "Skip to content You signed in with another tab or window. Download raw file " * 10}
    docs_store.save_doc(good, COIN, "wp:https://docs.ethena.fi/", manifest, True)
    docs_store.mark_keyword(manifest, "ethena", "wp:https://docs.ethena.fi/")
    gho = {"coin_id": "gho", "name": "GHO"}
    docs_store.save_doc(bad, gho, f"wp:{bad_url}", manifest, True)
    docs_store.mark_keyword(manifest, "gho", f"wp:{bad_url}")
    assert collect_whitepapers.prune(manifest) == 1
    assert [d["coin_id"] for d in docs_store.iter_docs()] == ["ethena"]
    assert manifest["gho"] == {"keywords": [], "titles": [], "page_ids": []}       # 다시 받을 수 있게 기록 해제
    assert "wp:https://docs.ethena.fi/" in manifest["ethena"]["keywords"]
    json.dumps(manifest)
