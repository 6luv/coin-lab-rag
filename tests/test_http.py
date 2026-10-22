"""NF2006 재시도 규칙 (네트워크 없이 응답을 흉내 낸다)."""
import pytest

from src.data_prep import http, wiki


class FakeResp:
    def __init__(self, status, headers=None, body=None):
        self.status_code, self.headers, self._body = status, headers or {}, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def make_client(monkeypatch, responses):
    sleeps = []
    monkeypatch.setattr(http.time, "sleep", lambda s: sleeps.append(s))
    c = http.PoliteClient(0, wait_429_sec=65)
    it = iter(responses)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: next(it))
    return c, sleeps


def test_retry_after_parsing():
    assert http.retry_after_seconds("1.5", 65) == 1.5
    assert http.retry_after_seconds(None, 65) == 65
    assert http.retry_after_seconds("garbage", 65) == 65


def test_429_then_success_uses_retry_after(monkeypatch):
    c, sleeps = make_client(monkeypatch, [FakeResp(429, {"Retry-After": "3"}), FakeResp(200, body={"ok": 1})])
    assert c.get_json("u") == {"ok": 1}
    assert sleeps == [3.0]


def test_all_429_raises_with_reason_and_no_final_sleep(monkeypatch):
    c, sleeps = make_client(monkeypatch, [FakeResp(429)] * c_max(monkeypatch))
    with pytest.raises(RuntimeError, match="429"):
        c.get_json("u")
    assert len(sleeps) == c.max_retries - 1


def c_max(monkeypatch):
    return http.PoliteClient(0).max_retries


def test_404_returns_none(monkeypatch):
    c, _ = make_client(monkeypatch, [FakeResp(404)])
    assert c.get_json("u") is None


def test_link_review_related_drops_item_doc():
    entry = {"wikidata": {"qid": "Q9"}, "kowiki": None, "enwiki": {"title": "KuCoin"},
             "link_review": {"decision": "related"}}
    assert wiki.flat(entry)["enwiki"] is None


def test_gms_base_url_adds_openai_target(monkeypatch):
    from src.config import openai_base_url

    monkeypatch.setenv("OPENAI_BASE_URL", "https://gms.ssafy.io/gmsapi/")
    assert openai_base_url() == "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    assert openai_base_url() == "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
    monkeypatch.delenv("OPENAI_BASE_URL")
    assert openai_base_url().endswith("/gmsapi/api.openai.com/v1")
