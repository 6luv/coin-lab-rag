"""외부 API 호출 공통부 (NF2006: 재시도·호출 간격·식별 정보)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from src.config import settings, user_agent


def retry_after_seconds(value: str | None, default: float) -> float:
    """Retry-After 헤더(초 또는 HTTP 날짜)를 초로 바꾼다. 해석할 수 없으면 default."""
    if not value:
        return default
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return default


class PoliteClient:
    """호스트별 최소 호출 간격을 지키고, 429/5xx/네트워크 오류는 기다렸다가 재시도한다."""

    def __init__(self, interval_sec: float, headers: dict | None = None, wait_429_sec: float = 65,
                 max_wait_sec: float | None = None, max_retries: int | None = None, timeout_sec: float | None = None):
        """max_wait_sec: 429 의 Retry-After 가 이보다 길면 기다리지 않고 실패로 돌려준다 (백서처럼 건별로 건너뛰어도 되는 호출)."""
        cfg = settings()["http"]
        self.interval = interval_sec
        self.wait_429 = wait_429_sec
        self.max_wait = max_wait_sec
        self.timeout = timeout_sec or cfg["timeout_sec"]
        self.max_retries = max_retries or cfg["max_retries"]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent(), "Accept": "application/json"})
        if headers:
            self.session.headers.update(headers)
        self._last = 0.0

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.interval:
            time.sleep(self.interval - gap)
        self._last = time.monotonic()

    def get_json(self, url: str, params: dict | None = None):
        r = self.get(url, params)
        return None if r is None else r.json()

    def get(self, url: str, params: dict | None = None, max_bytes: int | None = None) -> requests.Response | None:
        """재시도·간격 규칙을 지켜 GET. 404 는 None. max_bytes 를 넘는 본문은 ValueError (백서 PDF 등)."""
        last_error: object = None
        for attempt in range(1, self.max_retries + 1):
            is_last = attempt == self.max_retries
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=self.timeout, stream=max_bytes is not None)
            except requests.RequestException as e:  # 네트워크 오류
                last_error = e
                if not is_last:
                    time.sleep(2 * attempt)
                continue
            if r.status_code == 429:
                last_error = "HTTP 429 (호출 한도 초과)"
                if not is_last:
                    wait = retry_after_seconds(r.headers.get("Retry-After"), self.wait_429)
                    if self.max_wait is not None and wait > self.max_wait:
                        raise RuntimeError(f"HTTP 429, {wait:.0f}초 뒤 재시도 요구 (상한 {self.max_wait:.0f}초) — 이번에는 건너뜀: {url}")
                    print(f"  429 rate limited -> {wait:.0f}s 대기 후 재시도 ({attempt}/{self.max_retries})")
                    time.sleep(wait)
                continue
            if r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                if not is_last:
                    time.sleep(3 * attempt)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            if max_bytes is not None:
                body = bytearray()
                for part in r.iter_content(64 * 1024):
                    body.extend(part)
                    if len(body) > max_bytes:
                        r.close()
                        raise ValueError(f"본문이 너무 큼 (> {max_bytes // 1_000_000}MB): {url}")
                r._content = bytes(body)
            return r
        raise RuntimeError(f"요청 실패: {url} ({last_error})")
