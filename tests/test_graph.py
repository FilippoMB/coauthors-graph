from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from coauthors_graph.config import Config
from coauthors_graph.dblp import parse_person_xml
from coauthors_graph.graph import build_graph_document


FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def test_build_graph_counts_every_repeated_collaboration() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")
    config = Config(
        author_id="01/1",
        name_overrides={"02/2": "Bob Builder"},
        community_algorithm="greedy_modularity",
        community_resolution=1.5,
        layout_seed=42,
    )

    document = build_graph_document(
        profile,
        config,
        clock=lambda: datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
    )

    edges = {
        frozenset((edge["source"], edge["target"])): edge for edge in document["edges"]
    }
    assert edges[frozenset(("01/1", "02/2"))]["publication_count"] == 2
    assert edges[frozenset(("01/1", "03/3"))]["publication_count"] == 2
    assert edges[frozenset(("02/2", "03/3"))]["publication_count"] == 2
    assert edges[frozenset(("02/2", "03/3"))]["publication_ids"] == [
        "journals/example/ExampleBC24",
        "journals/corr/abs-2301-00001",
    ]


def test_build_graph_emits_versioned_deterministic_document() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")
    config = Config(
        author_id="01/1",
        name_overrides={"02/2": "Bob Builder"},
        community_algorithm="greedy_modularity",
        community_resolution=1.5,
        layout_seed=42,
    )

    def clock() -> datetime:
        return datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    first = build_graph_document(profile, config, clock=clock)
    second = build_graph_document(profile, config, clock=clock)

    assert first == second
    assert first["meta"] == {
        "schema_version": 1,
        "generated_at": "2026-07-10T12:00:00Z",
        "source_url": "https://dblp.org/pid/01/1.xml",
        "focal_author_id": "01/1",
        "publication_count": 3,
        "node_count": 4,
        "coauthor_count": 3,
        "edge_count": 4,
        "year_range": [2022, 2024],
    }
    nodes = {node["id"]: node for node in first["nodes"]}
    assert nodes["01/1"]["is_focal"] is True
    assert nodes["01/1"]["publication_count"] == 3
    assert nodes["02/2"]["label"] == "Bob Builder"
    assert nodes["02/2"]["short_label"] == "B. Builder"
    assert len(first["publications"]) == 3
