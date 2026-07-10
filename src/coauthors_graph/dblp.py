"""Fetch and parse a single DBLP person export."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from html import unescape
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DBLP_BASE_URL = "https://dblp.org"
SUPPORTED_RECORD_TYPES = frozenset({"article", "inproceedings"})
USER_AGENT = (
    "coauthors-graph/1.0 "
    "(+https://github.com/FilippoMB/coauthors-graph; weekly DBLP profile export)"
)


class DblpError(RuntimeError):
    """Raised when DBLP data cannot be fetched or parsed safely."""


@dataclass(frozen=True)
class Author:
    pid: str
    name: str


@dataclass(frozen=True)
class Publication:
    key: str
    title: str
    year: int
    venue: str
    url: str
    authors: tuple[Author, ...]


@dataclass(frozen=True)
class PersonProfile:
    pid: str
    name: str
    source_url: str
    publications: tuple[Publication, ...]


def person_export_url(author_id: str) -> str:
    return f"{DBLP_BASE_URL}/pid/{author_id}.xml"


def fetch_person_xml(
    author_id: str,
    *,
    session: requests.Session | None = None,
) -> bytes:
    """Fetch a DBLP person export, retrying only transient HTTP failures."""

    owned_session = session is None
    active_session = session or _retrying_session()
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
        source_url=person_export_url(expected_pid),
        publications=publications,
    )


def _retrying_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


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

        venue = _element_text(record.find("journal"))
        if not venue:
            venue = _element_text(record.find("booktitle")) or "DBLP"

        authors_by_pid: dict[str, Author] = {}
        for author_element in record.findall("author"):
            pid = _clean_text(author_element.get("pid"))
            name = _element_text(author_element)
            if not pid:
                raise DblpError(f"Publication {key} contains an author without a PID")
            if not name:
                raise DblpError(f"Publication {key} contains an author without a name")
            authors_by_pid.setdefault(pid, Author(pid=pid, name=name))

        if not authors_by_pid:
            raise DblpError(f"Publication {key} contains no authors")

        yield Publication(
            key=key,
            title=title,
            year=year,
            venue=venue,
            url=f"{DBLP_BASE_URL}/rec/{key}.html",
            authors=tuple(authors_by_pid.values()),
        )


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return _clean_text("".join(element.itertext()))


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(unescape(value).split())
