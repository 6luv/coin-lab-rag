"""프로젝트 백서(PDF·웹 문서) 수집 (F2016: 위키백과와 종류가 다른 문서 출처).

- 출처: CoinGecko 상세의 `links.whitepaper` URL (coins.json 의 `whitepaper`).
- PDF 는 쪽 단위 텍스트(`pages`)로 받아, 청크가 쪽을 넘지 않게 나누고 근거에 쪽 번호를 붙인다 (F2004 "파일명과 쪽").
- 웹 문서는 HTML 에서 본문 글자만 뽑는다. 스크립트로 그리는 페이지·스캔 PDF 처럼 글자가 적으면 수집하지 않는다.
- 저작권은 각 프로젝트에 있다. 교육용 검색 근거로만 쓰고, 받은 원문은 git 에 올리지 않는다 (data/docs/whitepaper/).
"""
from __future__ import annotations

import hashlib
import io
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from src.config import settings
from src.data_prep.http import PoliteClient

SOURCE = {"pdf": ("백서 PDF", "whitepaper_pdf"), "web": ("백서(웹)", "whitepaper_web")}
# 파일 미리보기·사이트 껍데기 화면에서 나오는 글자 (본문이 아니다)
VIEWER_TEXT = re.compile(
    r"You signed in with another tab or window|Download raw file|requires iframe|Sign in to GitHub|"
    r"You can.t perform that action at this time",
    re.I,
)


def resolve_url(url: str) -> str | None:
    """백서 링크를 실제 파일 주소로. GitHub 미리보기(blob)는 원본(raw) 파일로 바꾸고, 폴더(tree) 링크는 받지 않는다."""
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return None
    if u.netloc.lower() in ("github.com", "www.github.com"):
        parts = u.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":  # owner/repo/blob/ref/path...
            return f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/{'/'.join(parts[3:])}"
        if len(parts) >= 3 and parts[2] == "tree":  # 폴더: 어느 파일이 백서인지 알 수 없다
            return None
    return url


def looks_like_viewer(text: str) -> bool:
    return bool(VIEWER_TEXT.search(text[:3000]))
LICENSE = "저작권: 각 프로젝트 (교육용 근거 인용, 원문 재배포 안 함)"


def make_client() -> PoliteClient:
    """사이트마다 따로 받는 문서라, 한 곳이 느리거나 오래 기다리라고 하면 그 코인만 건너뛴다 (다음 실행 때 재시도)."""
    cfg = settings()["http"]
    return PoliteClient(
        cfg["whitepaper_interval_sec"],
        headers={"Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5"},
        wait_429_sec=10,
        max_wait_sec=cfg["whitepaper_max_wait_sec"],
        max_retries=2,
        timeout_sec=cfg["whitepaper_timeout_sec"],
    )


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "template"}
    BLOCK = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """HTML → (제목, 본문). 줄 안의 공백을 줄이고 빈 줄은 하나로 합친다."""
    parser = _TextExtractor()
    parser.feed(html)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(parser.parts).split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return parser.title.strip(), text


def pdf_pages(data: bytes, max_pages: int) -> list[dict]:
    from pypdf import PdfReader  # requirements.txt: pypdf (정의서 참고자료)

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages[:max_pages], 1):
        text = re.sub(r"[ \t]+", " ", page.extract_text() or "").strip()
        if text:
            pages.append({"page": i, "text": text})
    return pages


def _cap(pages: list[dict], max_chars: int) -> list[dict]:
    out, total = [], 0
    for p in pages:
        if total >= max_chars:
            break
        text = p["text"][: max_chars - total]
        out.append({**p, "text": text})
        total += len(text)
    return out


def fetch(client: PoliteClient, coin: dict, url: str) -> dict | None:
    """백서 1건을 받아 문서 레코드로. 글자가 너무 적거나 지원하지 않는 형식이면 None.

    네트워크 오류는 RuntimeError/requests 예외, 너무 큰 파일은 ValueError 로 올린다 (호출 측이 '다음에 재시도'로 처리).
    """
    fetch_url = resolve_url(url)
    if fetch_url is None:
        return None
    cfg = settings()["collect"]
    r = client.get(fetch_url, max_bytes=cfg["whitepaper_max_mb"] * 1_000_000)
    if r is None:
        return None
    ctype = (r.headers.get("Content-Type") or "").lower()
    body = r.content
    if "pdf" in ctype or body[:5] == b"%PDF-":
        try:
            pages = _cap(pdf_pages(body, cfg["whitepaper_max_pages"]), cfg["whitepaper_max_chars"])
        except Exception:  # 깨진·암호화된 PDF
            return None
        kind, title = "pdf", f"{coin['name']} 백서"
        file_name = urlparse(r.url).path.rsplit("/", 1)[-1] or "whitepaper.pdf"
        text = "\n\n".join(p["text"] for p in pages)
    elif "html" in ctype or "text/plain" in ctype:
        page_title, text = html_to_text(r.text)
        pages, kind, file_name = [], "web", ""
        title = f"{coin['name']} 백서" + (f" — {page_title[:80]}" if page_title else "")
        text = text[: cfg["whitepaper_max_chars"]]
    else:
        return None
    if len(text) < cfg["whitepaper_min_chars"] or looks_like_viewer(text):
        return None
    source, source_type = SOURCE[kind]
    doc = {
        "page_id": hashlib.sha1(url.encode()).hexdigest()[:12],
        "title": title,
        "url": url,
        "text": text,
        "source": source,
        "source_type": source_type,
        "license": LICENSE,
        "lastrevid": None,
    }
    if pages:
        doc["pages"] = pages
        doc["file_name"] = file_name
    return doc
