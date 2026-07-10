"""Fetch and normalize an author's Semantic Scholar publications."""

from __future__ import annotations

import re
from typing import Any

import requests

from .http import retrying_session
from .models import Author, PersonProfile, Publication


API_BASE_URL = "https://api.semanticscholar.org/graph/v1"
SITE_BASE_URL = "https://www.semanticscholar.org"
PAGE_SIZE = 1000
PAPER_FIELDS = (
    "paperId,title,year,venue,publicationVenue,externalIds,authors,"
    "publicationTypes,journal"
)
USER_AGENT = (
    "coauthors-graph/2.0 "
    "(+https://github.com/FilippoMB/coauthors-graph; weekly metadata refresh)"
)


class SemanticScholarError(RuntimeError):
    """Raised when Semantic Scholar data cannot be fetched or normalized."""


def author_papers_url(author_id: str) -> str:
    return f"{API_BASE_URL}/author/{author_id}/papers"


def author_page_url(author_id: str) -> str:
    return f"{SITE_BASE_URL}/author/{author_id}"


def fetch_author_profile(
    author_id: str,
    *,
    api_key: str | None = None,
    session: requests.Session | None = None,
) -> PersonProfile:
    """Fetch every page of an author's papers and normalize the records."""

    if not author_id.isdigit():
        raise SemanticScholarError(
            "Semantic Scholar author ID must contain only digits"
        )

    owned_session = session is None
    active_session = session or retrying_session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if api_key and api_key.strip():
        headers["x-api-key"] = api_key.strip()

    publications: list[Publication] = []
    seen_paper_ids: set[str] = set()
    seen_offsets: set[int] = set()
    offset = 0
    focal_names: list[str] = []

    try:
        while True:
            if offset in seen_offsets:
                raise SemanticScholarError(
                    f"Semantic Scholar pagination repeated offset {offset}"
                )
            seen_offsets.add(offset)

            payload = _fetch_page(
                active_session,
                author_id,
                offset=offset,
                headers=headers,
            )
            records = payload.get("data")
            if not isinstance(records, list):
                raise SemanticScholarError(
                    "Semantic Scholar response is missing its paper list"
                )

            for record in records:
                publication = _parse_publication(record, author_id)
                if publication.semantic_scholar_id in seen_paper_ids:
                    raise SemanticScholarError(
                        "Semantic Scholar pagination repeated paper "
                        f"{publication.semantic_scholar_id}"
                    )
                seen_paper_ids.add(publication.semantic_scholar_id or "")
                publications.append(publication)
                focal_name = next(
                    (
                        author.name
                        for author in publication.authors
                        if author.pid == f"s2:{author_id}"
                    ),
                    "",
                )
                if focal_name:
                    focal_names.append(focal_name)

            next_offset = payload.get("next")
            if next_offset is None:
                break
            if (
                not isinstance(next_offset, int)
                or isinstance(next_offset, bool)
                or next_offset < 0
            ):
                raise SemanticScholarError(
                    "Semantic Scholar returned an invalid pagination offset"
                )
            offset = next_offset
    finally:
        if owned_session:
            active_session.close()

    if not publications:
        raise SemanticScholarError(
            f"Semantic Scholar author {author_id} contains no publications"
        )
    if not focal_names:
        raise SemanticScholarError(
            f"Semantic Scholar author {author_id} is absent from returned papers"
        )

    return PersonProfile(
        pid=f"s2:{author_id}",
        name=_preferred_name(focal_names),
        source_urls=(author_page_url(author_id),),
        publications=tuple(publications),
    )


def _fetch_page(
    session: requests.Session,
    author_id: str,
    *,
    offset: int,
    headers: dict[str, str],
) -> dict[str, Any]:
    try:
        response = session.get(
            author_papers_url(author_id),
            params={"limit": PAGE_SIZE, "offset": offset, "fields": PAPER_FIELDS},
            headers=headers,
            timeout=(5, 30),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise SemanticScholarError(
            f"Could not fetch Semantic Scholar author {author_id}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise SemanticScholarError("Semantic Scholar returned malformed JSON data")
    return payload


def _parse_publication(record: Any, expected_author_id: str) -> Publication:
    if not isinstance(record, dict):
        raise SemanticScholarError("Semantic Scholar returned an invalid paper record")

    paper_id = _required_text(record, "paperId")
    title = _required_text(record, "title")
    year = record.get("year")
    if not isinstance(year, int) or isinstance(year, bool):
        raise SemanticScholarError(
            f"Semantic Scholar paper {paper_id} has no valid year"
        )

    raw_authors = record.get("authors")
    if not isinstance(raw_authors, list) or not raw_authors:
        raise SemanticScholarError(f"Semantic Scholar paper {paper_id} has no authors")

    authors_by_id: dict[str, Author] = {}
    for raw_author in raw_authors:
        if not isinstance(raw_author, dict):
            raise SemanticScholarError(
                f"Semantic Scholar paper {paper_id} has an invalid author"
            )
        name = _required_text(raw_author, "name")
        author_id = _optional_text(raw_author.get("authorId"))
        if not author_id:
            raise SemanticScholarError(
                f"Semantic Scholar paper {paper_id} has an author without an ID"
            )
        pid = f"s2:{author_id}"
        authors_by_id.setdefault(pid, Author(pid=pid, name=name))

    if f"s2:{expected_author_id}" not in authors_by_id:
        raise SemanticScholarError(
            f"Semantic Scholar paper {paper_id} omits requested author "
            f"{expected_author_id}"
        )

    external_ids = _external_ids(record.get("externalIds"), paper_id)
    external_id_map = dict(external_ids)
    doi = _normalize_doi(external_id_map.get("DOI"))
    arxiv_doi: str | None = None
    arxiv_id = _normalize_arxiv_id(external_id_map.get("ArXiv"))
    if doi and doi.startswith("10.48550/arxiv."):
        arxiv_doi = doi
        arxiv_id = arxiv_id or _normalize_arxiv_id(doi.removeprefix("10.48550/arxiv."))
        doi = None
    arxiv_id = arxiv_id or _arxiv_id_from_dblp(external_id_map.get("DBLP"))

    venue = _venue(record)
    record_type = _record_type(record)
    is_preprint = _is_preprint(
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        publication_venue=record.get("publicationVenue"),
    )
    if is_preprint:
        venue = "Arxiv"

    if doi:
        url = f"https://doi.org/{doi}"
    elif arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        url = f"{SITE_BASE_URL}/paper/{paper_id}"

    normalized_external_ids = dict(external_ids)
    normalized_external_ids["SemanticScholar"] = paper_id
    if doi:
        normalized_external_ids["DOI"] = doi
    elif "DOI" in normalized_external_ids:
        del normalized_external_ids["DOI"]
    if arxiv_doi:
        normalized_external_ids["ArXivDOI"] = arxiv_doi
    if arxiv_id:
        normalized_external_ids["ArXiv"] = arxiv_id

    return Publication(
        key=f"s2:{paper_id}",
        title=title,
        year=year,
        venue=venue,
        url=url,
        authors=tuple(authors_by_id.values()),
        source="semantic_scholar",
        record_type=record_type,
        doi=doi,
        arxiv_id=arxiv_id,
        semantic_scholar_id=paper_id,
        is_preprint=is_preprint,
        external_ids=tuple(sorted(normalized_external_ids.items())),
        provenance=("semantic_scholar",),
        source_ids=(f"s2:{paper_id}",),
    )


def _external_ids(value: Any, paper_id: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise SemanticScholarError(
            f"Semantic Scholar paper {paper_id} has invalid external identifiers"
        )

    identifiers: list[tuple[str, str]] = []
    for key, raw_value in value.items():
        if not isinstance(key, str) or raw_value is None:
            continue
        text = str(raw_value).strip()
        if text:
            identifiers.append((key.strip(), text))
    return tuple(sorted(identifiers))


def _venue(record: dict[str, Any]) -> str:
    candidates = [record.get("venue")]
    for field in ("journal", "publicationVenue"):
        value = record.get(field)
        if isinstance(value, dict):
            candidates.append(value.get("name"))

    venue = next(
        (
            candidate.strip()
            for candidate in candidates
            if isinstance(candidate, str) and candidate.strip()
        ),
        "Semantic Scholar",
    )
    return "Arxiv" if venue.casefold() in {"arxiv", "arxiv.org", "corr"} else venue


def _record_type(record: dict[str, Any]) -> str:
    mappings = {
        "journalarticle": "article",
        "conference": "inproceedings",
        "book": "book",
        "booksection": "incollection",
        "dataset": "data",
        "thesis": "thesis",
        "editorial": "editorial",
        "review": "review",
        "casereport": "case-report",
        "clinicaltrial": "clinical-trial",
        "lettersandcomments": "letter",
        "metaanalysis": "meta-analysis",
        "news": "news",
        "study": "study",
    }
    publication_venue = record.get("publicationVenue")
    if isinstance(publication_venue, dict):
        venue_type = publication_venue.get("type")
        if isinstance(venue_type, str):
            normalized = _type_key(venue_type)
            if "conference" in normalized:
                return "inproceedings"
            if "journal" in normalized:
                return "article"
            if "book" in normalized:
                return "book"

    values = record.get("publicationTypes")
    if isinstance(values, list):
        normalized_types = {
            _type_key(value) for value in values if isinstance(value, str)
        }
        for source_type in (
            "conference",
            "journalarticle",
            "booksection",
            "book",
            "dataset",
            "thesis",
            "editorial",
            "review",
            "casereport",
            "clinicaltrial",
            "lettersandcomments",
            "metaanalysis",
            "news",
            "study",
        ):
            if source_type in normalized_types:
                return mappings[source_type]
    return "scholarly-output"


def _is_preprint(
    *,
    venue: str,
    doi: str | None,
    arxiv_id: str | None,
    publication_venue: Any,
) -> bool:
    if doi:
        return False
    if isinstance(publication_venue, dict):
        venue_type = publication_venue.get("type")
        if isinstance(venue_type, str) and any(
            word in _type_key(venue_type) for word in ("journal", "conference", "book")
        ):
            return False
    normalized_venue = venue.casefold()
    if normalized_venue in {"arxiv", "arxiv.org", "corr"}:
        return True
    return bool(arxiv_id and normalized_venue == "semantic scholar")


def _required_text(record: dict[str, Any], field: str) -> str:
    value = _optional_text(record.get(field))
    if not value:
        raise SemanticScholarError(
            f"Semantic Scholar paper is missing required field {field}"
        )
    return value


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    return normalized.rstrip(".,;)") or None


def _normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    for prefix in (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "arxiv:",
    ):
        if normalized.casefold().startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    normalized = normalized.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", normalized, flags=re.I) or None


def _arxiv_id_from_dblp(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"journals/corr/abs-(\d{4})-(\d{4,5})(?:v\d+)?", value, re.I)
    if not match:
        return None
    return f"{match.group(1)}.{match.group(2)}"


def _type_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _preferred_name(names: list[str]) -> str:
    counts = {name: names.count(name) for name in set(names)}
    return sorted(counts, key=lambda name: (-counts[name], name))[0]
