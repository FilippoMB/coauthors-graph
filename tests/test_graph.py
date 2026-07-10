from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from coauthors_graph.config import Config
from coauthors_graph.dblp import parse_person_xml
from coauthors_graph.graph import (
    GraphError,
    _validate_publication_url,
    build_graph_document,
)


FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def config() -> Config:
    return Config(
        author_id="01/1",
        semantic_scholar_author_id="100",
        minimum_publication_year=2013,
        name_overrides={"02/2": "Bob Builder"},
        author_id_overrides={},
        excluded_publication_ids=(),
        duplicate_groups=(),
        community_algorithm="greedy_modularity",
        community_resolution=1.5,
        layout_seed=42,
    )


def test_build_graph_counts_every_repeated_collaboration() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")
    document = build_graph_document(
        profile,
        config(),
        clock=lambda: datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
    )

    edges = {
        frozenset((edge["source"], edge["target"])): edge for edge in document["edges"]
    }
    assert edges[frozenset(("01/1", "02/2"))]["publication_count"] == 2
    assert edges[frozenset(("01/1", "03/3"))]["publication_count"] == 2
    assert edges[frozenset(("02/2", "03/3"))]["publication_count"] == 2
    assert edges[frozenset(("02/2", "03/3"))]["publication_ids"] == [
        "dblp:journals/example/ExampleBC24",
        "dblp:journals/corr/abs-2301-00001",
    ]


def test_build_graph_emits_versioned_deterministic_document() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")

    def clock() -> datetime:
        return datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    first = build_graph_document(profile, config(), clock=clock)
    second = build_graph_document(profile, config(), clock=clock)

    assert first == second
    assert first["meta"] == {
        "schema_version": 2,
        "generated_at": "2026-07-10T12:00:00Z",
        "source_urls": ["https://dblp.org/pid/01/1.xml"],
        "focal_author_id": "01/1",
        "publication_count": 8,
        "node_count": 8,
        "coauthor_count": 7,
        "edge_count": 8,
        "year_range": [2017, 2024],
    }
    nodes = {node["id"]: node for node in first["nodes"]}
    assert nodes["01/1"]["is_focal"] is True
    assert nodes["01/1"]["short_label"] == "A. Example"
    assert nodes["01/1"]["publication_count"] == 8
    assert nodes["02/2"]["label"] == "Bob Builder"
    assert nodes["02/2"]["short_label"] == "B. Builder"
    assert len(first["publications"]) == 8
    article = next(
        publication
        for publication in first["publications"]
        if publication["doi"] == "10.1000/example.2024"
    )
    assert article["source"] == "dblp"
    assert article["record_type"] == "article"
    assert article["external_ids"]["DOI"] == ["10.1000/example.2024"]


@pytest.mark.parametrize(
    "url",
    [
        "https://dblp.org/rec/journals/example/Paper.html",
        "https://doi.org/10.1000/example",
        "https://arxiv.org/abs/2401.01234",
        "https://www.semanticscholar.org/paper/abc123",
    ],
)
def test_publication_url_validation_accepts_schema_v2_sources(url) -> None:
    _validate_publication_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://doi.org/10.1000/example",
        "https://doi.org.evil.example/10.1000/example",
        "https://dblp.org/pid/01/1",
        "https://arxiv.org/abs/",
        "javascript:alert(1)",
    ],
)
def test_publication_url_validation_rejects_unsafe_links(url) -> None:
    with pytest.raises(GraphError, match="Unsafe|missing an identifier"):
        _validate_publication_url(url)
