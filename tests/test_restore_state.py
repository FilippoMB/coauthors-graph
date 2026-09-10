from copy import deepcopy

import pytest
import requests

from automation.restore_state import restore
from coauthors_graph.state import StateError, load_state, write_json
from test_refresh import baseline


class Response:
    def __init__(self, value, status=200):
        self.value = value
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.value


class Session:
    def __init__(self, values):
        self.values = iter(values)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, *args, **kwargs):
        return next(self.values)


def setup(tmp_path, monkeypatch, responses):
    path = write_json(
        tmp_path / "config.json",
        {"author_id": "139/5968", "semantic_scholar_author_id": "14553624"},
    )
    monkeypatch.setattr(
        "automation.restore_state.retrying_session", lambda: Session(responses)
    )
    return str(path)


def test_first_migration_restores_existing_v2_graph(tmp_path, monkeypatch):
    cfg = setup(
        tmp_path, monkeypatch, [Response({}, 404), Response(baseline()["graph"])]
    )
    path = restore(tmp_path / "input", cfg)
    assert load_state(path, "139/5968")["graph"] == baseline()["graph"]


def test_regular_restore_uses_snapshot_without_fetching_graph(tmp_path, monkeypatch):
    saved = baseline()
    cfg = setup(tmp_path, monkeypatch, [Response(saved)])
    path = restore(tmp_path / "input", cfg)
    assert load_state(path, "139/5968") == saved


def test_missing_state_after_migration_fails_closed(tmp_path, monkeypatch):
    graph = deepcopy(baseline()["graph"])
    graph["meta"]["schema_version"] = 3
    cfg = setup(tmp_path, monkeypatch, [Response({}, 404), Response(graph)])
    with pytest.raises(StateError, match="missing source-state"):
        restore(tmp_path / "input", cfg)


def test_state_server_error_does_not_silently_bootstrap(tmp_path, monkeypatch):
    cfg = setup(tmp_path, monkeypatch, [Response({}, 503)])
    with pytest.raises(requests.HTTPError):
        restore(tmp_path / "input", cfg)
