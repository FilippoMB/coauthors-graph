from __future__ import annotations

from datetime import datetime, timezone

import pytest

from coauthors_graph.config import Config
from coauthors_graph.graph import build_graph_document
from coauthors_graph.merge import MergeError, combine_profiles
from coauthors_graph.models import Author, PersonProfile, Publication


def make_config(**changes) -> Config:
    values = {
        "author_id": "139/5968",
        "semantic_scholar_author_id": "14553624",
        "minimum_publication_year": 2013,
        "name_overrides": {},
        "author_id_overrides": {},
        "excluded_publication_ids": (),
        "duplicate_groups": (),
        "community_algorithm": "greedy_modularity",
        "community_resolution": 1.5,
        "layout_seed": 42,
    }
    values.update(changes)
    return Config(**values)


def publication(
    key: str,
    *,
    source: str,
    title: str,
    year: int,
    authors: list[tuple[str, str]],
    venue: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    is_preprint: bool = False,
    record_type: str = "article",
) -> Publication:
    prefix = "dblp" if source == "dblp" else "s2"
    canonical_key = f"{prefix}:{key}"
    semantic_id = key if source == "semantic_scholar" else None
    external_ids = [("DBLP", key)] if source == "dblp" else [("SemanticScholar", key)]
    if doi:
        external_ids.append(("DOI", doi))
    if arxiv_id:
        external_ids.append(("ArXiv", arxiv_id))
    if doi:
        url = f"https://doi.org/{doi}"
    elif arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    elif source == "dblp":
        url = f"https://dblp.org/rec/{key}.html"
    else:
        url = f"https://www.semanticscholar.org/paper/{key}"
    return Publication(
        key=canonical_key,
        title=title,
        year=year,
        venue=venue,
        url=url,
        authors=tuple(Author(pid=pid, name=name) for pid, name in authors),
        source=source,
        record_type=record_type,
        doi=doi,
        arxiv_id=arxiv_id,
        semantic_scholar_id=semantic_id,
        is_preprint=is_preprint,
        external_ids=tuple(external_ids),
        provenance=(source,),
        source_ids=(canonical_key,),
    )


def profiles(
    dblp_publications: list[Publication],
    semantic_publications: list[Publication],
) -> tuple[PersonProfile, PersonProfile]:
    return (
        PersonProfile(
            pid="139/5968",
            name="Filippo Maria Bianchi",
            source_urls=("https://dblp.org/pid/139/5968.xml",),
            publications=tuple(dblp_publications),
        ),
        PersonProfile(
            pid="s2:14553624",
            name="F. Bianchi",
            source_urls=("https://www.semanticscholar.org/author/14553624",),
            publications=tuple(semantic_publications),
        ),
    )


def test_applied_energy_preprint_and_formal_record_appear_exactly_once() -> None:
    dblp_authors = [
        ("01/odin", "Odin Foldvik Eikeland"),
        ("02/colin", "Colin C Kelsall"),
        ("03/kyle", "Kyle Buznitsky"),
        ("04/shomik", "Shomik Verma"),
        ("139/5968", "Filippo Maria Bianchi"),
        ("05/matteo", "Matteo Chiesa"),
        ("06/asegun", "Asegun Henry"),
    ]
    semantic_authors = [
        ("s2:1581621470", "Odin Foldvik Eikeland"),
        ("s2:2108486531", "Colin C. Kelsall"),
        ("s2:2171202275", "Kyle Buznitsky"),
        ("s2:2143867555", "Shomik Verma"),
        ("s2:14553624", "F. Bianchi"),
        ("s2:49753558", "Matteo Chiesa"),
        ("s2:5101962", "Asegun Henry"),
    ]
    preprint = publication(
        "journals/corr/abs-2302-01902",
        source="dblp",
        title="Power Availability of PV Plus Thermal Batteries in Real World Electric Power Grids",
        year=2023,
        authors=dblp_authors,
        venue="Arxiv",
        arxiv_id="2302.01902v1",
        is_preprint=True,
    )
    formal = publication(
        "6febc3cad68717fd8f023e05e68281ff87b54077",
        source="semantic_scholar",
        title="Power availability of PV plus thermal batteries in real-world electric power grids",
        year=2023,
        authors=semantic_authors,
        venue="Applied Energy",
        doi="10.1016/j.apenergy.2023.121572",
        arxiv_id="2302.01902",
    )

    merged = combine_profiles(*profiles([preprint], [formal]), make_config())

    assert len(merged.publications) == 1
    result = merged.publications[0]
    assert result.title == formal.title
    assert result.venue == "Applied Energy"
    assert result.url == "https://doi.org/10.1016/j.apenergy.2023.121572"
    assert result.doi == "10.1016/j.apenergy.2023.121572"
    assert result.arxiv_id == "2302.01902"
    assert result.is_preprint is False
    assert set(result.provenance) == {"dblp", "semantic_scholar"}

    document = build_graph_document(
        merged,
        make_config(),
        clock=lambda: datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    assert document["meta"]["publication_count"] == 1
    assert len(document["edges"]) == 21
    assert {edge["publication_count"] for edge in document["edges"]} == {1}
    output = document["publications"][0]
    assert output["external_ids"]["DOI"] == ["10.1016/j.apenergy.2023.121572"]
    assert output["external_ids"]["ArXiv"] == ["2302.01902", "2302.01902v1"]


def test_exact_cross_source_copies_merge_but_similar_formal_outputs_do_not() -> None:
    dblp_authors = [("139/5968", "Filippo Maria Bianchi"), ("02/2", "Lorenzo Livi")]
    s2_authors = [("s2:14553624", "F. Bianchi"), ("s2:999", "L. Livi")]
    exact_dblp = publication(
        "journal/exact",
        source="dblp",
        title="Graph-Based Energy: A Study.",
        year=2024,
        authors=dblp_authors,
        venue="Journal A",
    )
    exact_s2 = publication(
        "exact-copy",
        source="semantic_scholar",
        title="graph based energy a study",
        year=2024,
        authors=s2_authors,
        venue="Journal A",
    )
    extension = publication(
        "formal-extension",
        source="semantic_scholar",
        title="Graph Based Energy: An Extended Study",
        year=2025,
        authors=s2_authors,
        venue="Journal B",
        doi="10.1000/extension",
    )

    merged = combine_profiles(
        *profiles([exact_dblp], [exact_s2, extension]), make_config()
    )

    assert len(merged.publications) == 2
    assert {item.venue for item in merged.publications} == {"Journal A", "Journal B"}


def test_fuzzy_preprint_match_keeps_formal_metadata_and_standalone_arxiv() -> None:
    dblp_authors = [("139/5968", "Filippo Maria Bianchi"), ("02/2", "Lorenzo Livi")]
    s2_authors = [("s2:14553624", "F. Bianchi"), ("s2:999", "Lorenzo Livi")]
    formal = publication(
        "journal/modern-energy",
        source="dblp",
        title="Deep Learning for Modern Energy Systems",
        year=2024,
        authors=dblp_authors,
        venue="Energy Journal",
        doi="10.1000/modern",
    )
    matching_preprint = publication(
        "matching-preprint",
        source="semantic_scholar",
        title="Deep Learning for Modern Energy System",
        year=2022,
        authors=s2_authors,
        venue="Arxiv",
        arxiv_id="2201.00001",
        is_preprint=True,
    )
    standalone = publication(
        "standalone-preprint",
        source="semantic_scholar",
        title="A Completely Different Result",
        year=2024,
        authors=s2_authors,
        venue="Arxiv",
        arxiv_id="2401.00002",
        is_preprint=True,
    )

    merged = combine_profiles(
        *profiles([formal], [matching_preprint, standalone]), make_config()
    )

    assert len(merged.publications) == 2
    retained_formal = next(item for item in merged.publications if not item.is_preprint)
    retained_preprint = next(item for item in merged.publications if item.is_preprint)
    assert retained_formal.title == formal.title
    assert retained_formal.venue == "Energy Journal"
    assert retained_preprint.venue == "Arxiv"


def test_preprint_never_bridges_two_formal_outputs() -> None:
    dblp_authors = [("139/5968", "Filippo Maria Bianchi"), ("02/2", "Lorenzo Livi")]
    s2_authors = [("s2:14553624", "F. Bianchi"), ("s2:999", "Lorenzo Livi")]
    formal_one = publication(
        "conference/version",
        source="dblp",
        title="One Shared Title",
        year=2023,
        authors=dblp_authors,
        venue="Conference",
        doi="10.1000/conference",
    )
    formal_two = publication(
        "journal/version",
        source="dblp",
        title="One Shared Title",
        year=2023,
        authors=dblp_authors,
        venue="Journal",
        doi="10.1000/journal",
    )
    preprint = publication(
        "shared-preprint",
        source="semantic_scholar",
        title="One Shared Title",
        year=2023,
        authors=s2_authors,
        venue="Arxiv",
        arxiv_id="2301.00001",
        is_preprint=True,
    )

    unresolved = combine_profiles(
        *profiles([formal_one, formal_two], [preprint]), make_config()
    )
    assert len(unresolved.publications) == 3
    assert sum(not item.is_preprint for item in unresolved.publications) == 2

    resolved = combine_profiles(
        *profiles([formal_one, formal_two], [preprint]),
        make_config(
            duplicate_groups=(("dblp:conference/version", "s2:shared-preprint"),)
        ),
    )
    assert len(resolved.publications) == 2
    assert {item.venue for item in resolved.publications} == {"Conference", "Journal"}


def test_identity_overrides_resolve_ambiguous_initials() -> None:
    dblp = publication(
        "ambiguous",
        source="dblp",
        title="DBLP Work",
        year=2024,
        authors=[
            ("139/5968", "Filippo Maria Bianchi"),
            ("01/alex", "Alex Smith"),
            ("02/alex", "Avery Smith"),
        ],
        venue="Journal",
    )
    semantic = publication(
        "semantic-work",
        source="semantic_scholar",
        title="Supplemental Work",
        year=2025,
        authors=[("s2:14553624", "F. Bianchi"), ("s2:42", "A. Smith")],
        venue="Journal",
    )

    unmatched = combine_profiles(*profiles([dblp], [semantic]), make_config())
    supplemental = next(
        item for item in unmatched.publications if item.source != "dblp"
    )
    assert "s2:42" in {author.pid for author in supplemental.authors}

    overridden = combine_profiles(
        *profiles([dblp], [semantic]),
        make_config(author_id_overrides={"42": "01/alex"}),
    )
    supplemental = next(
        item for item in overridden.publications if item.source != "dblp"
    )
    assert "01/alex" in {author.pid for author in supplemental.authors}


def test_year_filter_and_exclusions_apply_before_deduplication() -> None:
    dblp = publication(
        "current",
        source="dblp",
        title="Current DBLP Work",
        year=2024,
        authors=[("139/5968", "Filippo Maria Bianchi")],
        venue="Journal",
    )
    old = publication(
        "old",
        source="semantic_scholar",
        title="Old Work",
        year=2012,
        authors=[("s2:14553624", "F. Bianchi")],
        venue="Journal",
    )
    excluded = publication(
        "excluded",
        source="semantic_scholar",
        title="Excluded Work",
        year=2023,
        authors=[("s2:14553624", "F. Bianchi")],
        venue="Journal",
        doi="10.1000/excluded",
    )
    retained = publication(
        "retained",
        source="semantic_scholar",
        title="Retained Work",
        year=2025,
        authors=[("s2:14553624", "F. Bianchi")],
        venue="Journal",
    )

    merged = combine_profiles(
        *profiles([dblp], [old, excluded, retained]),
        make_config(excluded_publication_ids=("DOI:10.1000/EXCLUDED",)),
    )

    assert {item.title for item in merged.publications} == {
        "Current DBLP Work",
        "Retained Work",
    }


def test_absent_explicit_duplicate_identifier_is_a_safe_noop() -> None:
    dblp = publication(
        "one",
        source="dblp",
        title="One",
        year=2024,
        authors=[("139/5968", "Filippo Maria Bianchi")],
        venue="Journal",
    )
    semantic = publication(
        "two",
        source="semantic_scholar",
        title="Two",
        year=2024,
        authors=[("s2:14553624", "F. Bianchi")],
        venue="Journal",
    )

    merged = combine_profiles(
        *profiles([dblp], [semantic]),
        make_config(duplicate_groups=(("dblp:one", "missing"),)),
    )

    assert len(merged.publications) == 2


def test_duplicate_semantic_scholar_dois_merge_and_input_order_is_irrelevant() -> None:
    dblp = publication(
        "primary",
        source="dblp",
        title="Primary Work",
        year=2024,
        authors=[("139/5968", "Filippo Maria Bianchi")],
        venue="Journal",
    )
    authors = [("s2:14553624", "F. Bianchi"), ("s2:999", "Lorenzo Livi")]
    first = publication(
        "duplicate-one",
        source="semantic_scholar",
        title="A DOI Work",
        year=2023,
        authors=authors,
        venue="Journal",
        doi="10.1000/DUPLICATE",
    )
    second = publication(
        "duplicate-two",
        source="semantic_scholar",
        title="A DOI Work",
        year=2023,
        authors=authors,
        venue="Journal",
        doi="https://doi.org/10.1000/duplicate",
    )

    forward = combine_profiles(*profiles([dblp], [first, second]), make_config())
    reverse = combine_profiles(*profiles([dblp], [second, first]), make_config())

    assert forward == reverse
    assert len(forward.publications) == 2
    doi_work = next(item for item in forward.publications if item.doi)
    assert set(doi_work.source_ids) == {"s2:duplicate-one", "s2:duplicate-two"}


def test_similar_preprints_with_different_arxiv_ids_remain_distinct() -> None:
    dblp = publication(
        "primary",
        source="dblp",
        title="Primary Work",
        year=2024,
        authors=[("139/5968", "Filippo Maria Bianchi")],
        venue="Journal",
    )
    authors = [("s2:14553624", "F. Bianchi"), ("s2:999", "Lorenzo Livi")]
    first = publication(
        "preprint-one",
        source="semantic_scholar",
        title="Deep Kernelized Autoencoders",
        year=2017,
        authors=authors,
        venue="Arxiv",
        arxiv_id="1702.02526",
        is_preprint=True,
    )
    second = publication(
        "preprint-two",
        source="semantic_scholar",
        title="The Deep Kernelized Autoencoder",
        year=2018,
        authors=authors,
        venue="Arxiv",
        arxiv_id="1807.07868",
        is_preprint=True,
    )

    merged = combine_profiles(*profiles([dblp], [first, second]), make_config())

    assert len(merged.publications) == 3


def test_filtered_dblp_aliases_cannot_create_current_identity_collisions() -> None:
    current = publication(
        "current",
        source="dblp",
        title="Current DBLP Work",
        year=2024,
        authors=[
            ("139/5968", "Filippo Maria Bianchi"),
            ("01/current", "Avery Smith"),
        ],
        venue="Journal",
    )
    old = publication(
        "old",
        source="dblp",
        title="Old DBLP Work",
        year=2012,
        authors=[
            ("139/5968", "Filippo Maria Bianchi"),
            ("02/old", "Alex Smith"),
        ],
        venue="Journal",
    )
    semantic = publication(
        "supplemental",
        source="semantic_scholar",
        title="Current Supplemental Work",
        year=2025,
        authors=[("s2:14553624", "F. Bianchi"), ("s2:42", "A. Smith")],
        venue="Journal",
    )

    merged = combine_profiles(*profiles([current, old], [semantic]), make_config())

    supplemental = next(
        item
        for item in merged.publications
        if item.title == "Current Supplemental Work"
    )
    assert "01/current" in {author.pid for author in supplemental.authors}
    assert all(item.year >= 2013 for item in merged.publications)


def test_name_override_must_target_a_retained_dblp_author() -> None:
    dblp = publication(
        "current",
        source="dblp",
        title="Current DBLP Work",
        year=2024,
        authors=[("139/5968", "Filippo Maria Bianchi")],
        venue="Journal",
    )
    semantic = publication(
        "supplemental",
        source="semantic_scholar",
        title="Current Supplemental Work",
        year=2025,
        authors=[("s2:14553624", "F. Bianchi")],
        venue="Journal",
    )

    with pytest.raises(MergeError, match="not a retained DBLP author"):
        combine_profiles(
            *profiles([dblp], [semantic]),
            make_config(name_overrides={"missing/pid": "A. Smith"}),
        )
