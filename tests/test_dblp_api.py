from copy import deepcopy
from pathlib import Path

import pytest

from coauthors_graph.dblp import DblpError, parse_person_xml
from coauthors_graph.dblp_api import (
    TYPE_NAMES,
    fetch_dblp_profile,
    fetch_sparql_profile,
    parse_sparql_rows,
)
from test_semantic_scholar import FakeSession


POLAR_AUTHOR_IDS = ["445/1583", "250/9150", "53/1616", "139/5968"]


def polar_rows(kind="Article"):
    rows = []
    for ordinal, (pid, name) in enumerate(
        [
            ("445/1583", "Andrea Federici"),
            ("250/9150", "Jakob Grahn"),
            ("53/1616", "Giacomo Boracchi"),
            ("139/5968", "Filippo Maria Bianchi"),
        ],
        start=1,
    ):
        values = {
            "publication": "https://dblp.org/rec/journals/corr/abs-2608-14366",
            "title": "Weakly Supervised Polar Low Segmentation in Sentinel-1 SAR Imagery.",
            "year": "2026",
            "type": f"http://purl.org/net/nknouf/ns/bibtex#{kind}",
            "venue": "CoRR",
            "doi": "https://doi.org/10.48550/ARXIV.2608.14366",
            "author": f"https://dblp.org/pid/{pid}",
            "name": name,
            "role": "https://dblp.org/rdf/schema#authoredBy",
            "ordinal": str(ordinal),
        }
        rows.append({key: {"value": value} for key, value in values.items()})
    return rows


@pytest.mark.parametrize("kind", TYPE_NAMES)
def test_query_preserves_types_and_pids(kind):
    rows = polar_rows(kind)
    if kind == "Proceedings":
        for row in rows:
            row["role"]["value"] = "https://dblp.org/rdf/schema#editedBy"
    profile = parse_sparql_rows(rows, "139/5968")
    paper = profile.publications[0]
    assert paper.record_type == TYPE_NAMES[kind]
    assert paper.venue == "Arxiv"
    assert paper.arxiv_id == "2608.14366"
    assert paper.doi is None
    assert [author.pid for author in paper.authors] == POLAR_AUTHOR_IDS


def test_query_requests_byline_ordinals_and_preserves_order_across_pages(monkeypatch):
    monkeypatch.setattr("coauthors_graph.dblp_api.PAGE_SIZE", 3)
    rows = polar_rows()
    # Metadata joins may repeat a contributor, and a byline can span pages.
    session = FakeSession(
        [
            {"results": {"bindings": [rows[3], rows[1], rows[0]]}},
            {"results": {"bindings": [rows[1], rows[2]]}},
        ]
    )
    profile = fetch_sparql_profile("139/5968", session=session)
    assert [a.pid for a in profile.publications[0].authors] == POLAR_AUTHOR_IDS
    assert len(session.calls) == 2
    for _, call in session.calls:
        query = call["params"]["query"]
        assert "dblp:signatureOrdinal ?ordinal" in query
        assert "dblp:AuthorSignature" in query
        assert "dblp:EditorSignature" in query


def test_byline_ordinals_are_numeric_not_lexical():
    rows = polar_rows()
    for ordinal in range(5, 13):
        row = deepcopy(rows[0])
        row["author"]["value"] = f"https://dblp.org/pid/999/{ordinal}"
        row["name"]["value"] = f"Contributor {ordinal}"
        row["ordinal"]["value"] = str(ordinal)
        rows.append(row)
    paper = parse_sparql_rows(rows[::-1], "139/5968").publications[0]
    assert [a.pid for a in paper.authors] == [
        *POLAR_AUTHOR_IDS,
        *(f"999/{n}" for n in range(5, 13)),
    ]


@pytest.mark.parametrize("ordinal", [None, "", "0", "-1", "first", "2", "5"])
def test_missing_invalid_or_conflicting_byline_order_is_not_guessed(ordinal):
    rows = polar_rows()
    bad = deepcopy(rows)
    for row in bad:
        row["publication"]["value"] = "https://dblp.org/rec/invalid-order"
    if ordinal is None:
        del bad[0]["ordinal"]
    else:
        bad[0]["ordinal"]["value"] = ordinal
    profile = parse_sparql_rows([*rows, *bad], "139/5968")
    assert len(profile.publications) == 1
    assert profile.rejected_count == 1
    assert not profile.complete
    assert "contributor order" in profile.warnings[0]


def test_html_challenge_is_an_explicit_source_failure():
    data = (Path(__file__).parent / "fixtures/dblp_challenge.html").read_bytes()
    with pytest.raises(DblpError, match="HTML challenge"):
        parse_person_xml(data, "139/5968")


def test_invalid_records_do_not_discard_healthy_ones():
    rows = polar_rows()
    bad = {
        **rows[0],
        "publication": {"value": "https://dblp.org/rec/invalid"},
        "year": {"value": "bad"},
    }
    profile = parse_sparql_rows([*rows, bad], "139/5968")
    assert len(profile.publications) == 1
    assert profile.rejected_count == 1
    assert not profile.complete


def test_xml_fallback_when_query_api_fails(monkeypatch):
    def fail(*args, **kwargs):
        raise DblpError("query unavailable")

    monkeypatch.setattr("coauthors_graph.dblp_api.fetch_sparql_profile", fail)
    monkeypatch.setattr(
        "coauthors_graph.dblp_api.fetch_person_xml",
        lambda *a, **k: (
            Path(__file__).parent / "fixtures/dblp_person.xml"
        ).read_bytes(),
    )
    assert fetch_dblp_profile("01/1").name == "Alice Example"
