from __future__ import annotations

from coauthors_graph.http import retrying_session


def test_retrying_session_bounds_transient_retries() -> None:
    session = retrying_session()
    try:
        retry = session.get_adapter("https://").max_retries
        assert retry.total == 3
        assert retry.connect == 3
        assert retry.read == 3
        assert retry.status == 3
        assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
        assert retry.respect_retry_after_header is True
        assert set(retry.allowed_methods) == {"GET"}
    finally:
        session.close()
