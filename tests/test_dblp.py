from __future__ import annotations

from pathlib import Path

import pytest
import requests

from coauthors_graph.dblp import DblpError, fetch_person_xml, parse_person_xml


FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def test_parse_person_xml_includes_supported_publications() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")

    assert profile.pid == "01/1"
    assert profile.name == "Alice Example"
    assert len(profile.publications) == 3
    assert {publication.key for publication in profile.publications} == {
        "journals/example/ExampleBC24",
        "journals/corr/abs-2301-00001",
        "conf/example/ExampleD22",
    }
    assert profile.publications[0].title == "Graph Models with H2O."


@pytest.mark.parametrize(
    "xml_data, message",
    [
        (b"<broken", "malformed XML"),
        (b"<other />", "Unexpected DBLP XML root"),
        (
            b'<dblpperson name="Alice" pid="01/1"><r><book /></r></dblpperson>',
            "no supported publications",
        ),
    ],
)
def test_parse_person_xml_rejects_unusable_data(xml_data, message) -> None:
    with pytest.raises(DblpError, match=message):
        parse_person_xml(xml_data, "01/1")


class FailingSession:
    def get(self, *args, **kwargs):
        raise requests.Timeout("timed out")


def test_fetch_person_xml_reports_network_errors() -> None:
    with pytest.raises(DblpError, match="Could not fetch DBLP profile"):
        fetch_person_xml("01/1", session=FailingSession())
