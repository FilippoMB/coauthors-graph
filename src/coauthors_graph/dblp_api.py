"""Read DBLP's supported SPARQL API, with its XML export as a fallback."""

from collections import defaultdict
import re
import xml.etree.ElementTree as ET

import requests

from .dblp import (
    DblpError,
    USER_AGENT,
    _parse_publications,
    fetch_person_xml,
    parse_person_xml,
)
from .http import retrying_session
from .models import PersonProfile


ENDPOINT = "https://sparql.dblp.org/sparql"
PAGE_SIZE = 2000
TYPE_NAMES = {
    "Article": "article",
    "Inproceedings": "inproceedings",
    "Incollection": "incollection",
    "Book": "book",
    "Proceedings": "proceedings",
    "Phdthesis": "phdthesis",
    "Mastersthesis": "mastersthesis",
    "Data": "data",
    "Dataset": "data",
}


def fetch_dblp_profile(author_id: str, *, session=None) -> PersonProfile:
    owned = session is None
    active = session or retrying_session()
    try:
        try:
            return fetch_sparql_profile(author_id, session=active)
        except DblpError as primary_error:
            try:
                return parse_person_xml(
                    fetch_person_xml(author_id, session=active), author_id
                )
            except DblpError as fallback_error:
                raise DblpError(
                    f"Query API: {primary_error}; XML fallback: {fallback_error}"
                ) from fallback_error
    finally:
        if owned:
            active.close()


def fetch_sparql_profile(author_id: str, *, session) -> PersonProfile:
    if not re.fullmatch(r"[A-Za-z0-9/-]+", author_id):
        raise DblpError("Invalid DBLP PID")
    query = f"""PREFIX dblp: <https://dblp.org/rdf/schema#>
SELECT DISTINCT ?publication ?title ?year ?type ?venue ?doi ?document ?author ?name ?role ?ordinal WHERE {{
  ?publication (dblp:authoredBy|dblp:editedBy) <https://dblp.org/pid/{author_id}> .
  OPTIONAL {{ ?publication dblp:title ?title }}
  OPTIONAL {{ ?publication dblp:yearOfPublication ?year }}
  OPTIONAL {{ ?publication dblp:bibtexType ?type }}
  OPTIONAL {{ ?publication dblp:publishedIn ?venue }}
  OPTIONAL {{ ?publication dblp:doi ?doi }}
  OPTIONAL {{ ?publication dblp:documentPage ?document }}
  OPTIONAL {{
    ?publication ?role ?author .
    VALUES (?role ?signatureType) {{
      (dblp:authoredBy dblp:AuthorSignature)
      (dblp:editedBy dblp:EditorSignature)
    }}
    OPTIONAL {{ ?author dblp:primaryCreatorName ?name }}
    OPTIONAL {{
      ?publication dblp:hasSignature ?signature .
      ?signature a ?signatureType ;
        dblp:signatureCreator ?author ;
        dblp:signatureOrdinal ?ordinal .
    }}
  }}
}} ORDER BY ?publication ?role ?ordinal ?author ?title ?year ?type ?venue ?doi ?document ?name
"""
    rows = []
    seen_pages = set()
    for offset in range(0, PAGE_SIZE * 100, PAGE_SIZE):
        try:
            response = session.get(
                ENDPOINT,
                params={"query": f"{query} LIMIT {PAGE_SIZE} OFFSET {offset}"},
                headers={
                    "Accept": "application/sparql-results+json",
                    "User-Agent": USER_AGENT,
                },
                timeout=(5, 30),
            )
            response.raise_for_status()
            payload = response.json()
            page = payload["results"]["bindings"]
            if not isinstance(page, list):
                raise ValueError("bindings must be an array")
            fingerprint = repr(page)
            if page and fingerprint in seen_pages:
                raise ValueError("repeated result page")
            seen_pages.add(fingerprint)
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return parse_sparql_rows(rows, author_id)
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            raise DblpError(f"Could not read DBLP query results: {error}") from error
    raise DblpError("DBLP query exceeded pagination limit")


def parse_sparql_rows(rows: list, author_id: str) -> PersonProfile:
    records = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or not _value(row, "publication").startswith(
            "https://dblp.org/rec/"
        ):
            raise DblpError("Invalid publication identifier in DBLP query results")
        records[_value(row, "publication")].append(row)
    publications, warnings, names = [], [], set()
    for uri, copies in sorted(records.items()):
        key = uri.removeprefix("https://dblp.org/rec/")
        try:
            kinds = {_value(row, "type").split("#")[-1] for row in copies}
            supported = sorted(kinds & TYPE_NAMES.keys())
            if not supported:
                raise DblpError(
                    f"Unsupported or missing DBLP record type for {key}: {sorted(kinds)}"
                )
            record = ET.Element(TYPE_NAMES[supported[0]], key=key)
            for field, tag in (
                ("title", "title"),
                ("year", "year"),
                ("venue", "journal"),
            ):
                values = {_value(row, field) for row in copies} - {""}
                if field != "venue" and len(values) != 1:
                    raise DblpError(f"Missing or conflicting {field} for {key}")
                if values:
                    ET.SubElement(record, tag).text = sorted(values)[0]
            contributors = _ordered_contributors(copies, key)
            if not any(pid == author_id for pid, _, _ in contributors):
                raise DblpError(f"Requested author missing from {key}")
            for pid, name, role in contributors:
                ET.SubElement(record, role, pid=pid).text = name
                if pid == author_id:
                    names.add(name)
            for link in sorted(
                {_value(row, field) for row in copies for field in ("doi", "document")}
                - {""}
            ):
                ET.SubElement(record, "ee").text = link
            root = ET.Element("dblpperson")
            ET.SubElement(root, "r").append(record)
            publications.extend(_parse_publications(root))
        except DblpError as error:
            warnings.append(str(error))
    if not publications or not names:
        raise DblpError(
            "DBLP query returned no usable publications for the focal author"
        )
    return PersonProfile(
        author_id,
        sorted(names)[0],
        (ENDPOINT,),
        tuple(publications),
        tuple(warnings),
        len(warnings),
        not warnings,
    )


def _ordered_contributors(rows: list[dict], key: str) -> list[tuple[str, str, str]]:
    """Use DBLP's byline ordinals, never query row order or lexical PID order."""
    by_role = {"author": {}, "editor": {}}
    roles = {
        "https://dblp.org/rdf/schema#authoredBy": "author",
        "https://dblp.org/rdf/schema#editedBy": "editor",
    }
    for row in rows:
        uri = _value(row, "author")
        pid = uri.removeprefix("https://dblp.org/pid/")
        name = _value(row, "name")
        if not pid or not name or not uri.startswith("https://dblp.org/pid/"):
            raise DblpError(f"Missing contributor identity for {key}")
        role = roles.get(_value(row, "role"))
        ordinal = _value(row, "ordinal")
        if role is None or not re.fullmatch(r"[1-9][0-9]*", ordinal):
            raise DblpError(f"Missing or invalid contributor order for {key}")
        positions = by_role[role]
        contributor = (pid, name, role)
        previous = positions.setdefault(int(ordinal), contributor)
        if previous != contributor:
            raise DblpError(f"Conflicting contributor order for {key}")

    contributors = []
    for positions in by_role.values():
        ordered = [positions[position] for position in sorted(positions)]
        if set(positions) != set(range(1, len(positions) + 1)) or len(
            {pid for pid, _, _ in ordered}
        ) != len(ordered):
            raise DblpError(f"Incomplete or conflicting contributor order for {key}")
        contributors.extend(ordered)
    return contributors


def _value(row: dict, key: str) -> str:
    value = row.get(key, {})
    if not isinstance(value, dict) or not isinstance(value.get("value", ""), str):
        raise DblpError(f"Invalid DBLP binding for {key}")
    return value.get("value", "")
