"""Validated, portable source snapshots stored with the static Pages deployment."""

from dataclasses import asdict
from datetime import datetime
from collections import defaultdict
from itertools import combinations
import json
import math
from pathlib import Path
from typing import Any

from .graph import GraphError, _validate_publication_url
from .models import Author, PersonProfile, Publication


STATE_VERSION = 1


class StateError(ValueError):
    """Saved state cannot safely be used as the next refresh's baseline."""


def read_json(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StateError(f"Cannot read saved data {path}: {error}") from error
    if not isinstance(value, dict):
        raise StateError("Saved data must be a JSON object")
    return value


def timestamp(value: Any, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise StateError("Invalid saved timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError as error:
        raise StateError("Invalid saved timestamp") from error
    return value


def text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError("Missing or invalid text in saved publication data")
    return value


def strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise StateError("Expected an array of identifiers")
    return tuple(text(item) for item in value)


def publication_from_dict(value: Any) -> Publication:
    if not isinstance(value, dict):
        raise StateError("Invalid saved publication")
    try:
        authors = tuple(
            Author(text(a["pid"]), text(a["name"])) for a in value["authors"]
        )
        if not authors or len({a.pid for a in authors}) != len(authors):
            raise StateError("Invalid or repeated saved contributor")
        year = value["year"]
        if type(year) is not int or not 1000 <= year <= 9999:
            raise StateError("Invalid saved publication year")
        if type(value["is_preprint"]) is not bool:
            raise StateError("Invalid saved preprint flag")
        _validate_publication_url(text(value["url"]))
        external = value["external_ids"]
        if not isinstance(external, list) or any(
            not isinstance(pair, list) or len(pair) != 2 for pair in external
        ):
            raise StateError("Invalid saved external IDs")
        optional = {
            key: value.get(key) for key in ("doi", "arxiv_id", "semantic_scholar_id")
        }
        for item in optional.values():
            if item is not None:
                text(item)
        return Publication(
            key=text(value["key"]),
            title=text(value["title"]),
            year=year,
            venue=text(value["venue"]),
            url=value["url"],
            authors=authors,
            source=text(value["source"]),
            record_type=text(value["record_type"]),
            is_preprint=value["is_preprint"],
            external_ids=tuple((text(k), text(v)) for k, v in external),
            provenance=strings(value["provenance"]),
            source_ids=strings(value["source_ids"]),
            **optional,
        )
    except (KeyError, TypeError, GraphError) as error:
        raise StateError(f"Invalid saved publication: {error}") from error


def profile_to_dict(profile: PersonProfile) -> dict:
    return json.loads(json.dumps(asdict(profile)))


def profile_from_dict(value: Any) -> PersonProfile:
    if not isinstance(value, dict):
        raise StateError("Invalid saved profile")
    try:
        records = tuple(publication_from_dict(p) for p in value["publications"])
        if len({p.key for p in records}) != len(records):
            raise StateError("Repeated publication IDs in saved profile")
        return PersonProfile(
            text(value["pid"]),
            text(value["name"]),
            strings(value["source_urls"]),
            records,
        )
    except (KeyError, TypeError) as error:
        raise StateError(f"Invalid saved profile: {error}") from error


def validate_graph(document: dict, focal_id: str) -> PersonProfile:
    """Import v2/v3 public graph records without discarding merged identifiers."""
    try:
        meta = document["meta"]
        if meta["schema_version"] not in {2, 3} or meta["focal_author_id"] != focal_id:
            raise StateError("Graph schema or focal author does not match")
        timestamp(meta["generated_at"])
        authors = {
            text(n["id"]): Author(n["id"], text(n["label"])) for n in document["nodes"]
        }
        if len(authors) != len(document["nodes"]) or focal_id not in authors:
            raise StateError("Invalid graph authors")
        if (
            meta["node_count"] != len(authors)
            or meta["coauthor_count"] != len(authors) - 1
        ):
            raise StateError("Invalid graph node counts")
        for node in document["nodes"]:
            text(node["short_label"])
            if node["is_focal"] != (node["id"] == focal_id) or any(
                type(node[key]) not in (int, float) or not math.isfinite(node[key])
                for key in ("x", "y")
            ):
                raise StateError("Invalid graph node geometry or focal flag")
        publications = []
        for value in document["publications"]:
            record = dict(
                value,
                key=value["id"],
                authors=[asdict(authors[pid]) for pid in value["author_ids"]],
                external_ids=[
                    [key, item]
                    for key, values in value["external_ids"].items()
                    for item in values
                ],
            )
            publication = publication_from_dict(record)
            if focal_id not in {a.pid for a in publication.authors}:
                raise StateError("Saved publication omits the focal author")
            publications.append(publication)
        ids = {p.key for p in publications}
        if (
            not ids
            or len(ids) != len(publications)
            or len(ids) != meta["publication_count"]
        ):
            raise StateError("Invalid graph publication counts")
        expected_edges = defaultdict(set)
        node_publications = defaultdict(set)
        for publication in publications:
            for author in publication.authors:
                node_publications[author.pid].add(publication.key)
            for pair in combinations(sorted(a.pid for a in publication.authors), 2):
                expected_edges[pair].add(publication.key)
        seen_edges = set()
        for edge in document["edges"]:
            pair = tuple(sorted((edge["source"], edge["target"])))
            if (
                edge["source"] not in authors
                or edge["target"] not in authors
                or pair in seen_edges
                or pair not in expected_edges
                or set(edge["publication_ids"]) != expected_edges[pair]
                or len(edge["publication_ids"]) != len(expected_edges[pair])
                or edge["publication_count"] != len(expected_edges[pair])
            ):
                raise StateError("Broken graph edge references")
            seen_edges.add(pair)
        if seen_edges != set(expected_edges) or meta["edge_count"] != len(seen_edges):
            raise StateError("Missing or invalid collaboration edges")
        for node in document["nodes"]:
            if node["publication_count"] != len(node_publications[node["id"]]):
                raise StateError("Invalid node publication count")
        return PersonProfile(
            focal_id,
            authors[focal_id].name,
            strings(meta["source_urls"]),
            tuple(publications),
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise StateError(f"Invalid saved graph: {error}") from error


def empty_state(focal_id: str) -> dict:
    return {
        "state_version": STATE_VERSION,
        "focal_author_id": focal_id,
        "sources": {},
        "identity_map": {},
        "graph": None,
    }


def load_state(path: str | Path, focal_id: str) -> dict:
    state = read_json(path)
    try:
        if (
            state["state_version"] != STATE_VERSION
            or state["focal_author_id"] != focal_id
        ):
            raise StateError("Saved state version or focal author does not match")
        validate_graph(state["graph"], focal_id)
        if not isinstance(state["sources"], dict) or not isinstance(
            state["identity_map"], dict
        ):
            raise StateError("Invalid saved source/identity registry")
        for key, value in state["identity_map"].items():
            text(key)
            text(value)
        for name, source in state["sources"].items():
            if name not in {"dblp", "semantic_scholar", "arxiv", "baseline"}:
                raise StateError("Unknown source in saved state")
            profile_from_dict(source["profile"])
            timestamp(source["last_success_at"], nullable=True)
            timestamp(source["last_attempt_at"], nullable=True)
    except (KeyError, TypeError) as error:
        raise StateError(f"Invalid saved state: {error}") from error
    return state


def bootstrap_state(document: dict, focal_id: str) -> dict:
    profile = validate_graph(document, focal_id)
    state = empty_state(focal_id)
    state["graph"] = document
    state["sources"]["baseline"] = {
        "profile": profile_to_dict(profile),
        "last_success_at": document["meta"]["generated_at"],
        "last_attempt_at": None,
    }
    return state


def write_json(path: str | Path, value: dict) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(destination)
    return destination
