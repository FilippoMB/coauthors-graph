"""Fetch and parse a single DBLP person export."""

from __future__ import annotations

from collections.abc import Iterable
from html import unescape
import re
import xml.etree.ElementTree as ET

import requests

from .http import retrying_session
from .models import Author, PersonProfile, Publication


DBLP_BASE_URL = "https://dblp.org"
SUPPORTED_RECORD_TYPES = frozenset(
    {
        "article",
        "inproceedings",
        "incollection",
        "book",
        "proceedings",
        "phdthesis",
        "mastersthesis",
        "data",
    }
)
USER_AGENT = (
    "coauthors-graph/1.0 "
    "(+https://github.com/FilippoMB/coauthors-graph; weekly DBLP profile export)"
)


class DblpError(RuntimeError):
    """Raised when DBLP data cannot be fetched or parsed safely."""


def person_export_url(author_id: str) -> str:
    return f"{DBLP_BASE_URL}/pid/{author_id}.xml"


def fetch_person_xml(
    author_id: str,
    *,
    session: requests.Session | None = None,
) -> bytes:
    """Fetch a DBLP person export, retrying only transient HTTP failures."""

    owned_session = session is None
    active_session = session or retrying_session()
    url = person_export_url(author_id)
    try:
        response = active_session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/xml"},
            timeout=(5, 30),
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as error:
        raise DblpError(f"Could not fetch DBLP profile {author_id}: {error}") from error
    finally:
        if owned_session:
            active_session.close()


def parse_person_xml(xml_data: bytes, expected_pid: str) -> PersonProfile:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as error:
        raise DblpError(f"DBLP returned malformed XML: {error}") from error

    if root.tag != "dblpperson":
        raise DblpError(f"Unexpected DBLP XML root element: {root.tag}")

    person_pid = root.get("pid") or expected_pid
    person_name = _clean_text(root.get("name"))
    if not person_name:
        raise DblpError("DBLP profile does not contain a person name")

    publications = tuple(_parse_publications(root))
    if not publications:
        raise DblpError("DBLP profile contains no supported publications")
    if not any(
        any(author.pid == person_pid for author in publication.authors)
        for publication in publications
    ):
        raise DblpError(
            f"Focal author PID {person_pid} does not occur in supported publications"
        )

    return PersonProfile(
        pid=person_pid,
        name=person_name,
        source_urls=(person_export_url(expected_pid),),
        publications=publications,
    )


def _parse_publications(root: ET.Element) -> Iterable[Publication]:
    for wrapper in root.findall("r"):
        record = next(iter(wrapper), None)
        if record is None or record.tag not in SUPPORTED_RECORD_TYPES:
            continue

        key = _clean_text(record.get("key"))
        if not key:
            raise DblpError("Publication is missing its DBLP key")

        title = _element_text(record.find("title"))
        if not title:
            raise DblpError(f"Publication {key} is missing its title")

        year_text = _element_text(record.find("year"))
        try:
            year = int(year_text)
        except ValueError as error:
            raise DblpError(
                f"Publication {key} has an invalid year: {year_text!r}"
            ) from error

        venue = _publication_venue(record)

        authors_by_pid: dict[str, Author] = {}
        contributor_elements = (*record.findall("author"), *record.findall("editor"))
        for author_element in contributor_elements:
            pid = _clean_text(author_element.get("pid"))
            name = _element_text(author_element)
            if not pid:
                raise DblpError(f"Publication {key} contains an author without a PID")
            if not name:
                raise DblpError(f"Publication {key} contains an author without a name")
            authors_by_pid.setdefault(pid, Author(pid=pid, name=name))

        if not authors_by_pid:
            raise DblpError(f"Publication {key} contains no authors or editors")

        doi, arxiv_id = _external_identifiers(record)
        external_ids = [("DBLP", key)]
        if doi:
            external_ids.append(("DOI", doi))
        if arxiv_id:
            external_ids.append(("ArXiv", arxiv_id))

        yield Publication(
            key=f"dblp:{key}",
            title=title,
            year=year,
            venue=venue,
            url=f"{DBLP_BASE_URL}/rec/{key}.html",
            authors=tuple(authors_by_pid.values()),
            source="dblp",
            record_type=record.tag,
            doi=doi,
            arxiv_id=arxiv_id,
            is_preprint=venue == "Arxiv",
            external_ids=tuple(external_ids),
            provenance=("dblp",),
            source_ids=(f"dblp:{key}",),
        )


def _publication_venue(record: ET.Element) -> str:
    candidates = (
        _element_text(record.find("journal")),
        _element_text(record.find("booktitle")),
        _element_text(record.find("publisher")),
        _element_text(record.find("school")),
        _element_text(record.find("series")),
    )
    venue = next((candidate for candidate in candidates if candidate), "DBLP")
    return "Arxiv" if venue.casefold() == "corr" else venue


def _external_identifiers(record: ET.Element) -> tuple[str | None, str | None]:
    doi: str | None = None
    arxiv_id: str | None = None
    for element in record.findall("ee"):
        url = _element_text(element)
        doi_match = re.search(r"(?:doi\.org/|doi:)(10\.\d{4,9}/\S+)", url, re.I)
        if doi_match:
            candidate = doi_match.group(1).rstrip(".,;)").casefold()
            if candidate.startswith("10.48550/arxiv."):
                arxiv_id = candidate.removeprefix("10.48550/arxiv.")
            elif doi is None:
                doi = candidate

        arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", url, re.I)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1).removesuffix(".pdf")

    if arxiv_id:
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.I)
    return doi, arxiv_id


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return _clean_text("".join(element.itertext()))


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(unescape(value).split())
