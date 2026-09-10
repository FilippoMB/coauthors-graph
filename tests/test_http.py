from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests

from coauthors_graph.http import MetadataSession, retry_after_seconds


def response(status, headers=None):
    value = requests.Response()
    value.status_code = status
    value._content = b""
    value._content_consumed = True
    value.headers.update(headers or {})
    return value


def test_transient_retries_are_bounded(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        return response(503)

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr("coauthors_graph.http.time.sleep", lambda seconds: None)
    with MetadataSession() as session:
        assert session.get("https://example.test").status_code == 503
    assert len(calls) == 4
    assert calls[0]["timeout"] == (5, 30)


def test_retry_after_and_arxiv_spacing(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("coauthors_graph.http.time.monotonic", lambda: now[0])
    monkeypatch.setattr(
        "coauthors_graph.http.time.sleep",
        lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    replies = iter([response(429, {"Retry-After": "7"}), response(200), response(200)])
    calls = []

    def get(*args, **kwargs):
        calls.append(now[0])
        return next(replies)

    monkeypatch.setattr(requests.Session, "get", get)
    with MetadataSession(minimum_interval=3) as session:
        session.get("https://example.test")
        session.get("https://example.test")
    assert calls == [0, 7, 10]


def test_excessive_retry_after_uses_fallback_instead_of_retrying_early(monkeypatch):
    monkeypatch.setattr(
        requests.Session, "get", lambda *a, **k: response(429, {"Retry-After": "3600"})
    )
    with (
        MetadataSession() as session,
        pytest.raises(requests.Timeout, match="retry beyond"),
    ):
        session.get("https://example.test")


def test_expired_budget_never_starts_a_request():
    with (
        MetadataSession(budget=0) as session,
        pytest.raises(requests.Timeout, match="budget exhausted"),
    ):
        session.get("https://example.test")


def test_retry_after_http_date(monkeypatch):
    monkeypatch.setattr(
        "coauthors_graph.http.time.time",
        lambda: datetime(2026, 9, 10, tzinfo=timezone.utc).timestamp(),
    )
    assert retry_after_seconds("Thu, 10 Sep 2026 00:00:15 GMT") == 15
    assert retry_after_seconds("bad") is None
