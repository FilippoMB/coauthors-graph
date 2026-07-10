from __future__ import annotations

import json
from pathlib import Path

import pytest

from coauthors_graph import __main__ as cli
from coauthors_graph.semantic_scholar import SemanticScholarError


DBLP_FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def test_source_failure_leaves_previous_graph_file_untouched(
    tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "author_id": "01/1",
                "semantic_scholar_author_id": "100",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "graph.json"
    output.write_text('{"previous":true}', encoding="utf-8")
    monkeypatch.setattr(
        cli, "fetch_person_xml", lambda author_id: DBLP_FIXTURE.read_bytes()
    )

    def fail_semantic_scholar(author_id, *, api_key=None):
        raise SemanticScholarError("source unavailable")

    monkeypatch.setattr(cli, "fetch_author_profile", fail_semantic_scholar)

    with pytest.raises(SemanticScholarError, match="source unavailable"):
        cli.generate(config_path, output)

    assert output.read_text(encoding="utf-8") == '{"previous":true}'
