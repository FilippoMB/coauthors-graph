from __future__ import annotations

import json

import pytest

from coauthors_graph.config import ConfigError, load_config


def test_load_config_applies_defaults(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"author_id": "01/1", "semantic_scholar_author_id": "12345"}),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.author_id == "01/1"
    assert config.semantic_scholar_author_id == "12345"
    assert config.minimum_publication_year == 2013
    assert config.name_overrides == {}
    assert config.author_id_overrides == {}
    assert config.excluded_publication_ids == ()
    assert config.duplicate_groups == ()
    assert config.community_algorithm == "greedy_modularity"
    assert config.community_resolution == 1.5
    assert config.layout_seed == 42


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"author_id": ""},
        {"author_id": "01/1", "semantic_scholar_author_id": ""},
        {"author_id": "01/1", "semantic_scholar_author_id": "s2:123"},
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "name_overrides": [],
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "author_id_overrides": [],
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "author_id_overrides": {"not-numeric": "02/2"},
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "minimum_publication_year": True,
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "excluded_publication_ids": "x",
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "duplicate_groups": [["only-one"]],
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "community_algorithm": "unknown",
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "community_resolution": 0,
        },
        {
            "author_id": "01/1",
            "semantic_scholar_author_id": "1",
            "layout_seed": True,
        },
    ],
)
def test_load_config_rejects_invalid_values(tmp_path, config) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(path)
