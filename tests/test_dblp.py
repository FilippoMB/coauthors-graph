from __future__ import annotations

from pathlib import Path

import pytest
import requests

from coauthors_graph.dblp import DblpError, fetch_person_xml, parse_person_xml


FIXTURE = Path(__file__).parent / "fixtures" / "dblp_person.xml"


def test_parse_person_xml_includes_authored_and_edited_scholarly_outputs() -> None:
    profile = parse_person_xml(FIXTURE.read_bytes(), "01/1")

    assert profile.pid == "01/1"
    assert profile.name == "Alice Example"
    assert len(profile.publications) == 8
    assert {publication.key for publication in profile.publications} == {
        "dblp:journals/example/ExampleBC24",
        "dblp:journals/corr/abs-2301-00001",
        "dblp:conf/example/ExampleD22",
        "dblp:books/example/Example21",
        "dblp:conf/example/2020",
        "dblp:books/example/Chapter19",
        "dblp:data/example/Dataset18",
        "dblp:phd/example/Thesis17",
    }
    assert profile.publications[0].title == "Graph Models with H2O."
    assert profile.publications[0].doi == "10.1000/example.2024"
    preprint = profile.publications[1]
    assert preprint.venue == "Arxiv"
    assert preprint.is_preprint is True
    assert preprint.arxiv_id == "2301.00001"
    proceedings = next(
        publication
        for publication in profile.publications
        if publication.record_type == "proceedings"
    )
    assert [author.pid for author in proceedings.authors] == ["01/1", "06/6"]
    assert proceedings.venue == "EXAMPLE 2020"


@pytest.mark.parametrize(
    "xml_data, message",
    [
        (b"<broken", "malformed XML"),
        (b"<other />", "Unexpected DBLP XML root"),
        (
            b'<dblpperson name="Alice" pid="01/1"><r><www /></r></dblpperson>',
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
