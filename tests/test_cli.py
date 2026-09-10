from __future__ import annotations

import json
from pathlib import Path

import pytest

from coauthors_graph import __main__ as cli
from coauthors_graph.state import StateError


DBLP_FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def test_invalid_baseline_leaves_previous_graph_file_untouched(
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

    def must_not_fetch(*args, **kwargs):
        raise AssertionError("Invalid saved state must stop before live fetching")

    monkeypatch.setattr(cli, "refresh", must_not_fetch)
    with pytest.raises(StateError, match="Invalid saved graph"):
        cli.generate(config_path, output)

    assert output.read_text(encoding="utf-8") == '{"previous":true}'
