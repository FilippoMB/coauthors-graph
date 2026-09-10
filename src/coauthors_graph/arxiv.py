"""Discover publications directly through arXiv's public Atom interfaces."""

from dataclasses import replace
import re
import xml.etree.ElementTree as ET

import requests

from .config import Config
from .http import retrying_session
from .identity import normalized_name, provisional_id
from .models import Author, PersonProfile, Publication


API_URL = "https://export.arxiv.org/api/query"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "x": "http://arxiv.org/schemas/atom",
    "o": "http://a9.com/-/spec/opensearch/1.1/",
}
PAGE_SIZE = 100
USER_AGENT = "coauthors-graph/3.0 (+https://github.com/FilippoMB/coauthors-graph; weekly metadata refresh)"


class ArxivError(RuntimeError):
    """An arXiv request or record could not be validated."""


def fetch_arxiv_profile(config: Config, *, session=None) -> PersonProfile:
    active = session or retrying_session(minimum_interval=3)
    publications, warnings, urls = {}, [], []
    rejected = 0
    names = {normalized_name(name) for name in config.arxiv_author_names}
    try:
        if config.arxiv_orcid:
            url = f"https://arxiv.org/a/{config.arxiv_orcid}.atom2"
            urls.append(url)
            try:
                records, errors = parse_feed(
                    _fetch(active, url), config, names, combined_authors=True
                )
                publications.update((p.key, p) for p in records)
                warnings.extend(errors)
                rejected += len(errors)
            except ArxivError as error:
                warnings.append(f"ORCID feed: {error}")
        if names:
            urls.append(API_URL)
            query = " OR ".join(
                f'au:"{name.replace(chr(34), " ")}"'
                for name in config.arxiv_author_names
            )
            seen = set()
            try:
                for start in range(0, PAGE_SIZE * 100, PAGE_SIZE):
                    root = _fetch(
                        active,
                        API_URL,
                        params={
                            "search_query": query,
                            "start": start,
                            "max_results": PAGE_SIZE,
                            "sortBy": "submittedDate",
                            "sortOrder": "descending",
                        },
                    )
                    total_text = root.findtext("o:totalResults", namespaces=NS)
                    if total_text is None or not total_text.isdigit():
                        raise ArxivError("Search response has no valid result count")
                    entries = root.findall("a:entry", NS)
                    if not entries and start < int(total_text):
                        raise ArxivError(
                            "Search ended before all results were returned"
                        )
                    for entry in entries:
                        key = entry.findtext("a:id", namespaces=NS)
                        if key in seen:
                            raise ArxivError(
                                "Search repeated a publication across pages"
                            )
                        seen.add(key)
                    records, errors = parse_feed(root, config, names)
                    publications.update((p.key, p) for p in records)
                    warnings.extend(errors)
                    rejected += len(errors)
                    if start + len(entries) >= int(total_text):
                        break
                else:
                    raise ArxivError("Search exceeded pagination limit")
            except ArxivError as error:
                warnings.append(f"Author search: {error}")
    finally:
        if session is None:
            active.close()
    if not publications:
        raise ArxivError("No usable arXiv publications: " + "; ".join(warnings))
    return PersonProfile(
        config.author_id,
        config.arxiv_author_names[0] if names else "",
        tuple(urls),
        tuple(publications.values()),
        tuple(warnings),
        rejected,
        not warnings,
    )


def _fetch(session, url, **kwargs) -> ET.Element:
    try:
        response = session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
            timeout=(5, 30),
            **kwargs,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        if root.tag != f"{{{NS['a']}}}feed":
            raise ArxivError("Expected an Atom feed, not an HTML/error response")
        return root
    except (requests.RequestException, ET.ParseError) as error:
        raise ArxivError(f"Could not read arXiv feed: {error}") from error


def parse_feed(
    root: ET.Element,
    config: Config,
    focal_names: set[str],
    *,
    combined_authors: bool = False,
) -> tuple[list[Publication], list[str]]:
    publications, errors = [], []
    for entry in root.findall("a:entry", NS):
        try:
            publication = _parse_entry(entry, combined_authors=combined_authors)
            if publication.year < config.minimum_publication_year:
                continue
            focal = [
                a
                for a in publication.authors
                if any(_matches_focal(a.name, name) for name in focal_names)
            ]
            if len(focal) != 1:
                raise ArxivError(
                    f"{publication.key}: focal contributor could not be uniquely verified"
                )
            authors = tuple(
                Author(config.author_id, a.name) if a == focal[0] else a
                for a in publication.authors
            )
            publications.append(replace(publication, authors=authors))
        except ArxivError as error:
            errors.append(str(error))
    return publications, errors


def _matches_focal(candidate: str, expected: str) -> bool:
    left, right = normalized_name(candidate).split(), normalized_name(expected).split()
    return (
        len(left) == len(right)
        and left[-1:] == right[-1:]
        and all(
            a == b or (min(len(a), len(b)) == 1 and a[0] == b[0])
            for a, b in zip(left[:-1], right[:-1])
        )
    )


def _parse_entry(entry: ET.Element, *, combined_authors: bool = False) -> Publication:
    identifier = entry.findtext("a:id", default="", namespaces=NS)
    match = re.fullmatch(
        r"https?://arxiv.org/abs/((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))(?:v\d+)?",
        identifier,
    )
    if not match:
        raise ArxivError(f"Invalid arXiv entry identifier: {identifier}")
    arxiv_id = match[1]
    key = f"arxiv:{arxiv_id}"
    title = " ".join(entry.findtext("a:title", default="", namespaces=NS).split())
    published = entry.findtext("a:published", default="", namespaces=NS)
    names = [
        " ".join(a.findtext("a:name", default="", namespaces=NS).split())
        for a in entry.findall("a:author", NS)
    ]
    # The ORCID feed puts a comma-separated byline in one author element.
    # Search results instead use one element per author; never split those names.
    if combined_authors and len(names) == 1:
        names = [name.strip() for name in names[0].split(",")]
    if (
        not title
        or not re.match(r"\d{4}-\d{2}-\d{2}T", published)
        or not names
        or not all(names)
    ):
        raise ArxivError(f"{key}: missing title, publication date, or contributors")
    doi = entry.findtext("x:doi", namespaces=NS)
    doi = doi.strip().lower().removeprefix("https://doi.org/") if doi else None
    if doi and (
        doi.startswith("10.48550/arxiv.") or not re.fullmatch(r"10\.\d{4,9}/\S+", doi)
    ):
        doi = None
    external = [("ArXiv", arxiv_id)]
    if doi:
        external.append(("DOI", doi))
    # A journal reference on arXiv is not itself a full formal-publication record.
    return Publication(
        key,
        title,
        int(published[:4]),
        "Arxiv",
        f"https://arxiv.org/abs/{arxiv_id}",
        tuple(Author(provisional_id(key, name), name) for name in names),
        "arxiv",
        "article",
        doi=doi,
        arxiv_id=arxiv_id,
        is_preprint=True,
        external_ids=tuple(external),
        provenance=("arxiv",),
        source_ids=(key,),
    )
