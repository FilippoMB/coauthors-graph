from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import requests

from coauthors_graph.semantic_scholar import (
    PAGE_SIZE,
    SemanticScholarError,
    fetch_author_profile,
)


FIXTURE = Path(__file__).parent / "fixtures" / "semantic_scholar_pages.json"


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads) -> None:
        self.payloads = iter(payloads)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(next(self.payloads))


def test_fetch_author_profile_paginates_and_normalizes_records() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    session = FakeSession(pages)

    profile = fetch_author_profile("14553624", api_key="secret", session=session)

    assert profile.pid == "s2:14553624"
    assert profile.name == "F. Bianchi"
    assert len(profile.publications) == 3
    assert [call[1]["params"]["offset"] for call in session.calls] == [0, 2]
    assert session.calls[0][1]["params"]["limit"] == PAGE_SIZE
    assert session.calls[0][1]["headers"]["x-api-key"] == "secret"

    applied = profile.publications[0]
    assert applied.venue == "Applied Energy"
    assert applied.record_type == "article"
    assert applied.is_preprint is False
    assert applied.doi == "10.1016/j.apenergy.2023.121572"
    assert applied.arxiv_id == "2302.01902"
    assert applied.url == "https://doi.org/10.1016/j.apenergy.2023.121572"

    preprint = profile.publications[1]
    assert preprint.venue == "Arxiv"
    assert preprint.is_preprint is True
    assert preprint.doi is None
    assert preprint.arxiv_id == "2401.01234"
    assert preprint.url == "https://arxiv.org/abs/2401.01234"
    assert profile.publications[2].record_type == "book"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"data": []}, "contains no publications"),
        ({"data": "not-a-list"}, "missing its paper list"),
        ({"data": [], "next": "2"}, "invalid pagination offset"),
        (["not-an-object"], "malformed JSON data"),
    ],
)
def test_fetch_author_profile_rejects_unusable_responses(payload, message) -> None:
    with pytest.raises(SemanticScholarError, match=message):
        fetch_author_profile("14553624", session=FakeSession([payload]))


class FailingSession:
    def get(self, *args, **kwargs):
        raise requests.Timeout("timed out")


def test_fetch_author_profile_reports_network_errors() -> None:
    with pytest.raises(SemanticScholarError, match="Could not fetch Semantic Scholar"):
        fetch_author_profile("14553624", session=FailingSession())


def test_fetch_author_profile_rejects_non_numeric_author_ids() -> None:
    with pytest.raises(SemanticScholarError, match="only digits"):
        fetch_author_profile("s2:14553624", session=FakeSession([]))


def test_every_returned_paper_must_include_the_requested_author() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    invalid_record = deepcopy(pages[0]["data"][1])
    invalid_record["paperId"] = "unrelated"
    invalid_record["authors"] = [
        author
        for author in invalid_record["authors"]
        if author["authorId"] != "14553624"
    ]

    with pytest.raises(SemanticScholarError, match="omits requested author"):
        fetch_author_profile(
            "14553624",
            session=FakeSession([{"data": [pages[0]["data"][0], invalid_record]}]),
        )


def test_author_ids_are_required_for_stable_identity() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = deepcopy(pages[0]["data"][0])
    record["authors"][0]["authorId"] = None

    with pytest.raises(SemanticScholarError, match="author without an ID"):
        fetch_author_profile("14553624", session=FakeSession([{"data": [record]}]))


def test_repeated_paper_across_pages_fails_instead_of_hiding_page_drift() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = pages[0]["data"][0]
    payloads = [
        {"data": [record], "next": 1},
        {"data": [record]},
    ]

    with pytest.raises(SemanticScholarError, match="repeated paper"):
        fetch_author_profile("14553624", session=FakeSession(payloads))


def test_publication_venue_wins_over_multi_valued_type_order() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = deepcopy(pages[0]["data"][0])
    record["publicationVenue"]["type"] = "conference"
    record["publicationTypes"] = ["Journal Article", "Conference"]

    profile = fetch_author_profile(
        "14553624", session=FakeSession([{"data": [record]}])
    )

    assert profile.publications[0].record_type == "inproceedings"


def test_corr_external_id_recovers_arxiv_identity_and_preprint_status() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = deepcopy(pages[0]["data"][1])
    record["venue"] = "CoRR"
    record["externalIds"] = {"DBLP": "journals/corr/abs-2401-01234"}

    profile = fetch_author_profile(
        "14553624", session=FakeSession([{"data": [record]}])
    )

    preprint = profile.publications[0]
    assert preprint.is_preprint is True
    assert preprint.venue == "Arxiv"
    assert preprint.arxiv_id == "2401.01234"
    assert preprint.url == "https://arxiv.org/abs/2401.01234"


def test_arxiv_doi_is_retained_as_provenance_not_a_formal_doi() -> None:
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = pages[0]["data"][1]

    profile = fetch_author_profile(
        "14553624", session=FakeSession([{"data": [record]}])
    )

    preprint = profile.publications[0]
    assert preprint.doi is None
    assert dict(preprint.external_ids)["ArXivDOI"] == "10.48550/arxiv.2401.01234v2"
    assert dict(preprint.external_ids)["ArXiv"] == "2401.01234"
