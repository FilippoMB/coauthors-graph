from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import requests

from coauthors_graph.arxiv import (
    ArxivError,
    NS,
    _matches_focal,
    fetch_arxiv_profile,
    parse_feed,
)
from coauthors_graph.config import load_config


FIXTURE = Path(__file__).parent / "fixtures/arxiv_polar_low.xml"


def config():
    return replace(
        load_config(Path(__file__).parents[1] / "config.json"),
        name_overrides={},
        duplicate_groups=(),
    )


def root():
    return ET.fromstring(FIXTURE.read_bytes())


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        response = requests.Response()
        response.status_code = 200
        response._content = ET.tostring(value)
        return response


def test_polar_low_has_four_contributors_and_stable_identifiers():
    records, errors = parse_feed(root(), config(), {"filippo maria bianchi"})
    assert not errors
    paper = records[0]
    assert paper.key == "arxiv:2608.14366"
    assert paper.venue == "Arxiv"
    assert paper.is_preprint
    assert len(paper.authors) == 4
    assert paper.authors[-1].pid == "139/5968"
    assert all(a.pid.startswith("provisional:") for a in paper.authors[:-1])


def test_orcid_combined_byline_matches_search_api():
    feed = root()
    entry = feed.find("a:entry", NS)
    for author in entry.findall("a:author", NS):
        entry.remove(author)
    author = ET.SubElement(entry, f"{{{NS['a']}}}author")
    ET.SubElement(
        author, f"{{{NS['a']}}}name"
    ).text = "Andrea Federici, Jakob Grahn, Giacomo Boracchi, Filippo Maria Bianchi"
    session = Session([feed, root()])
    profile = fetch_arxiv_profile(config(), session=session)
    assert len(profile.publications) == 1
    assert len(profile.publications[0].authors) == 4
    assert profile.complete


def test_search_survives_orcid_outage():
    profile = fetch_arxiv_profile(
        config(), session=Session([requests.Timeout("offline"), root()])
    )
    assert len(profile.publications) == 1
    assert not profile.complete
    assert "ORCID feed" in profile.warnings[0]


def test_search_paginates_and_detects_repeated_pages(monkeypatch):
    monkeypatch.setattr("coauthors_graph.arxiv.PAGE_SIZE", 1)
    first = root()
    first.find("o:totalResults", NS).text = "2"
    second = deepcopy(first)
    second.find("a:entry/a:id", NS).text = "http://arxiv.org/abs/2606.20932v1"
    session = Session([first, second])
    profile = fetch_arxiv_profile(replace(config(), arxiv_orcid=""), session=session)
    assert len(profile.publications) == 2
    assert [call[1]["params"]["start"] for call in session.calls] == [0, 1]
    partial = fetch_arxiv_profile(
        replace(config(), arxiv_orcid=""), session=Session([first, first])
    )
    assert not partial.complete
    assert "repeated" in partial.warnings[0]


def test_empty_and_malformed_feeds_are_unavailable():
    feed = ET.Element(f"{{{NS['a']}}}feed")
    with pytest.raises(ArxivError, match="No usable"):
        fetch_arxiv_profile(replace(config(), arxiv_orcid=""), session=Session([feed]))


def test_focal_matching_accepts_initials_but_not_a_different_full_name():
    assert _matches_focal("Filippo M. Bianchi", "Filippo Maria Bianchi")
    assert not _matches_focal("Filippo Mauro Bianchi", "Filippo Maria Bianchi")
    assert not _matches_focal("F. Bianchi", "Filippo Maria Bianchi")


def test_year_and_unrelated_author_filters():
    feed = root()
    assert not parse_feed(
        feed,
        replace(config(), minimum_publication_year=2027),
        {"filippo maria bianchi"},
    )[0]
    entry = feed.find("a:entry", NS)
    entry.findall("a:author", NS)[-1].find("a:name", NS).text = "Someone Else"
    records, warnings = parse_feed(feed, config(), {"filippo maria bianchi"})
    assert not records
    assert "focal contributor" in warnings[0]
