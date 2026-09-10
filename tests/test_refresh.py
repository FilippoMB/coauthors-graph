from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from coauthors_graph.arxiv import parse_feed
from coauthors_graph.dblp import DblpError
from coauthors_graph.dblp_api import parse_sparql_rows
from coauthors_graph.graph import build_graph_document
from coauthors_graph.identity import provisional_id
from coauthors_graph.merge import reconcile_profiles
from coauthors_graph.models import Author, PersonProfile
from coauthors_graph.refresh import refresh
from coauthors_graph.semantic_scholar import fetch_author_profile
from coauthors_graph.state import (
    StateError,
    bootstrap_state,
    empty_state,
    load_state,
    validate_graph,
    write_json,
)
from test_arxiv import config, root
from test_dblp_api import POLAR_AUTHOR_IDS, polar_rows
from test_semantic_scholar import FakeSession


def clock():
    return datetime(2026, 9, 10, 12, tzinfo=timezone.utc)


def dblp():
    return parse_sparql_rows(polar_rows(), "139/5968")


def arxiv():
    publications, _ = parse_feed(root(), config(), {"filippo maria bianchi"})
    return PersonProfile(
        "139/5968",
        "Filippo Maria Bianchi",
        ("https://export.arxiv.org/api/query",),
        tuple(publications),
    )


def baseline():
    document = build_graph_document(
        dblp(), config(), clock=lambda: datetime(2026, 8, 31, tzinfo=timezone.utc)
    )
    document["meta"]["schema_version"] = 2
    return bootstrap_state(document, config().author_id)


def fail():
    raise DblpError("source unavailable")


def test_new_paper_deduplicates_across_dblp_arxiv_and_baseline():
    document, state = refresh(
        config(), baseline(), clock=clock, fetchers={"dblp": dblp, "arxiv": arxiv}
    )
    assert document["meta"]["publication_count"] == 1
    paper = document["publications"][0]
    assert paper["arxiv_id"] == "2608.14366"
    assert paper["provenance"] == ["dblp", "arxiv"]
    assert paper["author_ids"] == POLAR_AUTHOR_IDS
    assert len(document["edges"]) == 6
    assert all(edge["publication_count"] == 1 for edge in document["edges"])
    assert all(not node["id"].startswith("provisional:") for node in document["nodes"])
    assert (
        state["identity_map"][provisional_id("arxiv:2608.14366", "Andrea Federici")]
        == "445/1583"
    )


def test_refresh_repairs_saved_pid_sorted_bylines_and_persists_source_order(tmp_path):
    profile = dblp()
    paper = profile.publications[0]
    incorrect = replace(
        paper, authors=tuple(sorted(paper.authors, key=lambda a: a.pid))
    )
    old_profile = replace(profile, publications=(incorrect,))
    old_graph = build_graph_document(old_profile, config(), clock=clock)
    _, saved = refresh(
        config(),
        bootstrap_state(old_graph, config().author_id),
        clock=clock,
        fetchers={"dblp": lambda: old_profile},
    )
    document, state = refresh(
        config(), saved, clock=clock, fetchers={"dblp": dblp, "arxiv": arxiv}
    )
    assert document["publications"][0]["author_ids"] == POLAR_AUTHOR_IDS
    assert document["edges"] == old_graph["edges"]
    assert [
        a["pid"]
        for a in state["sources"]["dblp"]["profile"]["publications"][0]["authors"]
    ] == POLAR_AUTHOR_IDS
    restored = load_state(
        write_json(tmp_path / "state.json", state), config().author_id
    )
    cached, _ = refresh(config(), restored, clock=clock, fetchers={"dblp": fail})
    assert cached["publications"][0]["author_ids"] == POLAR_AUTHOR_IDS


def test_healthy_source_can_add_while_dblp_is_down():
    _, saved = refresh(config(), baseline(), clock=clock, fetchers={"dblp": dblp})
    paper = arxiv().publications[0]
    new = replace(
        paper,
        key="arxiv:2609.00001",
        arxiv_id="2609.00001",
        title="A genuinely new work",
        external_ids=(("ArXiv", "2609.00001"),),
        source_ids=("arxiv:2609.00001",),
    )
    incoming = replace(arxiv(), publications=(new,))
    document, state = refresh(
        config(), saved, clock=clock, fetchers={"dblp": fail, "arxiv": lambda: incoming}
    )
    assert document["meta"]["publication_count"] == 2
    assert document["meta"]["sources"]["dblp"]["status"] == "cached"
    assert state["sources"]["dblp"]["profile"] == saved["sources"]["dblp"]["profile"]


def test_all_sources_down_preserves_data_and_generation_timestamp():
    previous = baseline()
    document, state = refresh(
        config(), previous, clock=clock, fetchers={"dblp": fail, "arxiv": fail}
    )
    for key in ("publications", "nodes", "edges"):
        assert document[key] == previous["graph"][key]
    assert document["meta"]["generated_at"] == "2026-08-31T00:00:00Z"
    assert document["meta"]["last_checked_at"] == "2026-09-10T12:00:00Z"
    assert state["graph"] == document


def test_all_sources_down_without_baseline_fails():
    with pytest.raises(StateError, match="no valid saved graph"):
        refresh(config(), empty_state(config().author_id), fetchers={"dblp": fail})


def test_partial_records_retain_previous_versions_and_last_complete_fetch():
    _, saved = refresh(config(), baseline(), clock=clock, fetchers={"dblp": dblp})
    old = dblp().publications[0]
    changed = replace(old, title="Corrected title")
    partial = replace(
        dblp(),
        publications=(changed,),
        complete=False,
        rejected_count=1,
        warnings=("invalid other record",),
    )
    document, next_state = refresh(
        config(),
        saved,
        clock=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc),
        fetchers={"dblp": lambda: partial},
    )
    assert document["publications"][0]["title"] == "Corrected title"
    status = document["meta"]["sources"]["dblp"]
    assert status["status"] == "partial"
    assert status["last_success_at"] == saved["sources"]["dblp"]["last_success_at"]
    assert (
        next_state["sources"]["dblp"]["profile"]["publications"][0]["title"]
        == "Corrected title"
    )


def test_record_disappearing_from_complete_response_is_not_deleted():
    paper = dblp().publications[0]
    other = replace(
        paper,
        key="dblp:conf/other",
        title="Different work",
        source_ids=("dblp:conf/other",),
        external_ids=(("DBLP", "conf/other"),),
        arxiv_id=None,
        is_preprint=False,
    )
    two = replace(dblp(), publications=(paper, other))
    _, saved = refresh(
        config(), baseline(), clock=clock, fetchers={"dblp": lambda: two}
    )
    document, _ = refresh(config(), saved, clock=clock, fetchers={"dblp": dblp})
    assert document["meta"]["publication_count"] == 2
    assert document["meta"]["sources"]["dblp"]["retained_count"] == 1


def test_source_recovery_advances_freshness_automatically():
    _, saved = refresh(config(), baseline(), clock=clock, fetchers={"dblp": fail})
    document, _ = refresh(config(), saved, clock=clock, fetchers={"dblp": dblp})
    assert document["meta"]["sources"]["dblp"]["status"] == "fresh"
    assert (
        document["meta"]["sources"]["dblp"]["last_success_at"]
        == document["meta"]["last_checked_at"]
    )


def test_state_round_trip_and_corruption(tmp_path):
    document, saved = refresh(
        config(), baseline(), clock=clock, fetchers={"dblp": dblp}
    )
    output = write_json(tmp_path / "state.json", saved)
    assert load_state(output, config().author_id) == saved
    for mutate in (
        lambda s: s.update(state_version=999),
        lambda s: s.update(focal_author_id="wrong"),
        lambda s: s["sources"]["dblp"].update(last_success_at="not a timestamp"),
        lambda s: s["graph"]["publications"][0].update(url="javascript:alert(1)"),
    ):
        corrupted = deepcopy(saved)
        mutate(corrupted)
        write_json(output, corrupted)
        with pytest.raises(StateError):
            load_state(output, config().author_id)
    assert validate_graph(document, config().author_id).publications


def test_unexpected_programming_errors_are_not_hidden_as_outages():
    def broken():
        raise TypeError("implementation bug")

    with pytest.raises(TypeError, match="implementation bug"):
        refresh(config(), baseline(), fetchers={"dblp": broken})


def test_actual_missing_enrico_id_resolves_to_dblp():
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/semantic_scholar_missing_id.json"
        ).read_text()
    )
    semantic = fetch_author_profile("14553624", session=FakeSession([payload]))
    enrico = Author("143/2901", "Enrico De Santis")
    anchor = replace(
        dblp(),
        publications=(
            replace(
                dblp().publications[0],
                authors=(*dblp().publications[0].authors, enrico),
            ),
        ),
    )
    merged, aliases = reconcile_profiles(
        (anchor, semantic), config(), focal_name=anchor.name
    )
    provisional = semantic.publications[0].authors[1].pid
    assert aliases[provisional] == "143/2901"
    assert any(a.pid == "143/2901" for p in merged.publications for a in p.authors)


def test_ambiguous_provisional_author_is_not_forced_and_can_be_overridden():
    paper = dblp().publications[0]
    ambiguous = replace(
        paper, authors=(*paper.authors, Author("999/1", "Andrea Federici"))
    )
    anchor = replace(dblp(), publications=(ambiguous,))
    provisional = arxiv().publications[0].authors[0].pid
    _, aliases = reconcile_profiles((anchor, arxiv()), config(), focal_name=anchor.name)
    assert aliases[provisional] == provisional
    _, aliases = reconcile_profiles(
        (anchor, arxiv()),
        replace(config(), author_id_overrides={provisional: "445/1583"}),
        focal_name=anchor.name,
    )
    assert aliases[provisional] == "445/1583"


def test_formal_version_replaces_saved_preprint():
    preprint = dblp().publications[0]
    formal = replace(
        preprint,
        key="dblp:journals/formal",
        source_ids=("dblp:journals/formal",),
        external_ids=((*preprint.external_ids, ("DOI", "10.1000/polar"))),
        is_preprint=False,
        venue="Published Journal",
        doi="10.1000/polar",
        url="https://doi.org/10.1000/polar",
        authors=tuple(reversed(preprint.authors)),
    )
    document, _ = refresh(
        config(),
        baseline(),
        clock=clock,
        fetchers={"dblp": lambda: replace(dblp(), publications=(formal,))},
    )
    assert len(document["publications"]) == 1
    assert document["publications"][0]["venue"] == "Published Journal"
    assert document["publications"][0]["author_ids"] == list(reversed(POLAR_AUTHOR_IDS))
