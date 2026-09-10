from pathlib import Path

import pytest

from coauthors_graph.dblp import DblpError, parse_person_xml
from coauthors_graph.dblp_api import TYPE_NAMES, fetch_dblp_profile, parse_sparql_rows


def polar_rows(kind="Article"):
    rows = []
    for pid, name in [
        ("445/1583", "Andrea Federici"),
        ("250/9150", "Jakob Grahn"),
        ("53/1616", "Giacomo Boracchi"),
        ("139/5968", "Filippo Maria Bianchi"),
    ]:
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
    assert len(paper.authors) == 4


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
