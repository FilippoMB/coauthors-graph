"""Construct and serialize the collaboration graph."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Callable

import networkx as nx

from .config import Config
from .dblp import PersonProfile, Publication


class GraphError(RuntimeError):
    """Raised when a usable graph cannot be constructed."""


Clock = Callable[[], datetime]


def build_graph_document(
    profile: PersonProfile,
    config: Config,
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    graph, preferred_names = _build_network(profile.publications)
    if profile.pid not in graph:
        raise GraphError(f"Focal author PID {profile.pid} is absent from the graph")

    communities = _community_assignments(graph, config)
    positions = nx.spring_layout(
        graph,
        seed=config.layout_seed,
        weight="publication_count",
        scale=1000,
        iterations=300,
    )
    publications_by_id = {
        publication.key: publication for publication in profile.publications
    }
    generated_at = (clock or _utc_now)().astimezone(timezone.utc)

    nodes = []
    for pid in sorted(graph.nodes):
        publication_ids = graph.nodes[pid]["publication_ids"]
        label = _display_name(
            pid,
            profile,
            preferred_names,
            config.name_overrides,
        )
        x, y = positions[pid]
        nodes.append(
            {
                "id": pid,
                "label": label,
                "short_label": _short_label(label),
                "is_focal": pid == profile.pid,
                "community": communities[pid],
                "publication_count": len(publication_ids),
                "degree": graph.degree(pid),
                "x": round(float(x), 3),
                "y": round(float(y), 3),
            }
        )

    edges = []
    for source, target, attributes in sorted(
        graph.edges(data=True), key=lambda edge: tuple(sorted(edge[:2]))
    ):
        source, target = sorted((source, target))
        publication_ids = sorted(
            attributes["publication_ids"],
            key=lambda key: (-publications_by_id[key].year, key),
        )
        edges.append(
            {
                "id": f"{source}::{target}",
                "source": source,
                "target": target,
                "publication_count": attributes["publication_count"],
                "publication_ids": publication_ids,
            }
        )

    publications = [
        {
            "id": publication.key,
            "title": publication.title,
            "year": publication.year,
            "venue": publication.venue,
            "url": publication.url,
            "author_ids": [author.pid for author in publication.authors],
        }
        for publication in sorted(
            profile.publications,
            key=lambda item: (-item.year, item.key),
        )
    ]
    years = [publication.year for publication in profile.publications]

    return {
        "meta": {
            "schema_version": 1,
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "source_url": profile.source_url,
            "focal_author_id": profile.pid,
            "publication_count": len(publications),
            "node_count": len(nodes),
            "coauthor_count": len(nodes) - 1,
            "edge_count": len(edges),
            "year_range": [min(years), max(years)],
        },
        "nodes": nodes,
        "edges": edges,
        "publications": publications,
    }


def _build_network(
    publications: tuple[Publication, ...],
) -> tuple[nx.Graph, dict[str, str]]:
    graph = nx.Graph()
    names: dict[str, Counter[str]] = {}

    for publication in publications:
        author_ids = sorted(author.pid for author in publication.authors)
        for author in publication.authors:
            names.setdefault(author.pid, Counter())[author.name] += 1
            if author.pid not in graph:
                graph.add_node(author.pid, publication_ids=[])
            graph.nodes[author.pid]["publication_ids"].append(publication.key)

        for source, target in combinations(author_ids, 2):
            if graph.has_edge(source, target):
                edge = graph[source][target]
                edge["publication_count"] += 1
                edge["publication_ids"].append(publication.key)
            else:
                graph.add_edge(
                    source,
                    target,
                    publication_count=1,
                    publication_ids=[publication.key],
                )

    preferred_names = {
        pid: sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]
        for pid, counter in names.items()
    }
    return graph, preferred_names


def _community_assignments(graph: nx.Graph, config: Config) -> dict[str, int]:
    if graph.number_of_nodes() == 1 or graph.number_of_edges() == 0:
        communities = [frozenset(graph.nodes)]
    elif config.community_algorithm == "louvain":
        communities = nx.community.louvain_communities(
            graph,
            weight="publication_count",
            resolution=config.community_resolution,
            seed=config.layout_seed,
        )
    else:
        communities = nx.community.greedy_modularity_communities(
            graph,
            weight="publication_count",
            resolution=config.community_resolution,
        )

    ordered = sorted(
        (frozenset(community) for community in communities),
        key=lambda community: (-len(community), min(community)),
    )
    return {
        pid: community_id
        for community_id, community in enumerate(ordered)
        for pid in community
    }


def _display_name(
    pid: str,
    profile: PersonProfile,
    preferred_names: dict[str, str],
    overrides: dict[str, str],
) -> str:
    if pid in overrides:
        return overrides[pid]
    if pid == profile.pid:
        return profile.name
    return preferred_names[pid]


def _short_label(name: str) -> str:
    parts = name.split()
    if len(parts) < 2:
        return name
    initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
    return f"{initials} {parts[-1]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
