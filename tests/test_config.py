from __future__ import annotations

import json

import pytest

from coauthors_graph.config import ConfigError, load_config


def test_load_config_applies_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"author_id": "01/1"}), encoding="utf-8")

    config = load_config(path)

    assert config.author_id == "01/1"
    assert config.name_overrides == {}
    assert config.community_algorithm == "greedy_modularity"
    assert config.community_resolution == 1.5
    assert config.layout_seed == 42


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"author_id": ""},
        {"author_id": "01/1", "name_overrides": []},
        {"author_id": "01/1", "community_algorithm": "unknown"},
        {"author_id": "01/1", "community_resolution": 0},
        {"author_id": "01/1", "layout_seed": True},
    ],
)
def test_load_config_rejects_invalid_values(tmp_path, config) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)
