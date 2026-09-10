"""Independent source refreshes, durable recovery, and honest freshness metadata."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path

from .arxiv import ArxivError, fetch_arxiv_profile
from .config import Config
from .dblp import DblpError
from .dblp_api import fetch_dblp_profile
from .graph import build_graph_document
from .merge import reconcile_profiles
from .models import PersonProfile
from .semantic_scholar import SemanticScholarError, fetch_author_profile
from .state import StateError, profile_from_dict, profile_to_dict, validate_graph


SOURCE_ERRORS = (DblpError, SemanticScholarError, ArxivError)


def refresh(
    config: Config, previous: dict, *, clock=None, fetchers=None
) -> tuple[dict, dict]:
    """Return a fully validated graph/state pair; expected outages never erase data."""
    now = (
        (clock or (lambda: datetime.now(timezone.utc)))()
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    state = deepcopy(previous)
    fetchers = (
        fetchers
        if fetchers is not None
        else {
            "dblp": lambda: fetch_dblp_profile(config.author_id),
            "semantic_scholar": lambda: fetch_author_profile(
                config.semantic_scholar_author_id,
                api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
            ),
            **(
                {"arxiv": lambda: fetch_arxiv_profile(config)}
                if config.arxiv_orcid or config.arxiv_author_names
                else {}
            ),
        }
    )
    statuses = {}
    any_accepted = False
    for name, fetcher in fetchers.items():
        saved = state["sources"].get(name)
        old_profile = profile_from_dict(saved["profile"]) if saved else None
        old_records = (
            {p.key: p for p in old_profile.publications} if old_profile else {}
        )
        status = {
            "status": "unavailable",
            "last_attempt_at": now,
            "last_success_at": saved["last_success_at"] if saved else None,
            "accepted_count": 0,
            "rejected_count": 0,
            "retained_count": len(old_records),
            "added_count": 0,
            "warnings": [],
        }
        try:
            incoming = fetcher()
            expected_pid = (
                f"s2:{config.semantic_scholar_author_id}"
                if name == "semantic_scholar"
                else config.author_id
            )
            if incoming.pid != expected_pid or not incoming.publications:
                raise StateError(f"Invalid profile returned by {name}")
            new_records = {p.key: p for p in incoming.publications}
            retained = len(old_records.keys() - new_records.keys())
            status.update(
                status="fresh" if incoming.complete and not retained else "partial",
                accepted_count=len(new_records),
                rejected_count=incoming.rejected_count,
                retained_count=retained,
                added_count=len(new_records.keys() - old_records.keys()),
                warnings=list(incoming.warnings),
            )
            if incoming.complete:
                status["last_success_at"] = now
            if retained:
                status["warnings"].append(
                    f"Retained {retained} previously collected records absent from this response"
                )
            merged = replace(
                incoming, publications=tuple({**old_records, **new_records}.values())
            )
            state["sources"][name] = {
                "profile": profile_to_dict(merged),
                "last_attempt_at": now,
                "last_success_at": status["last_success_at"],
            }
            any_accepted = True
        except SOURCE_ERRORS as error:
            status["status"] = "cached" if old_records else "unavailable"
            status["warnings"].append(str(error))
            if saved:
                saved["last_attempt_at"] = now
        statuses[name] = status

    previous_graph = previous.get("graph")
    if not any_accepted:
        if previous_graph is None:
            raise StateError(
                "All publication sources failed and no valid saved graph is available"
            )
        document = deepcopy(previous_graph)
    else:
        profiles = tuple(
            profile_from_dict(value["profile"]) for value in state["sources"].values()
        )
        focal_name = _focal_name(profiles, config)
        combined, aliases = reconcile_profiles(profiles, config, focal_name=focal_name)
        state["identity_map"].update(aliases)
        document = build_graph_document(
            combined,
            config,
            clock=lambda: datetime.fromisoformat(now.replace("Z", "+00:00")),
        )
    document["meta"].update(schema_version=3, last_checked_at=now, sources=statuses)
    validate_graph(document, config.author_id)
    state["graph"] = document
    return document, state


def _focal_name(profiles: tuple[PersonProfile, ...], config: Config) -> str:
    candidates = [p.name for p in profiles if p.pid == config.author_id and p.name]
    if not candidates:
        candidates = [
            a.name
            for p in profiles
            for r in p.publications
            for a in r.authors
            if a.pid == f"s2:{config.semantic_scholar_author_id}"
        ]
    if not candidates:
        raise StateError("Cannot establish the focal author's name")
    return max(candidates, key=lambda name: (len(name), name))


def write_run_summary(document: dict) -> None:
    lines = [
        "## Publication refresh",
        "",
        "| Source | Status | Accepted | Rejected | Retained | Added |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for name, status in document["meta"]["sources"].items():
        lines.append(
            f"| {name} | {status['status']} | {status['accepted_count']} | {status['rejected_count']} | {status['retained_count']} | {status['added_count']} |"
        )
        print(
            f"{name}: {status['status']}; {status['accepted_count']} accepted, {status['retained_count']} retained"
        )
        for warning in status["warnings"]:
            # Escape workflow-command syntax; source text is never an Actions command.
            safe = (
                f"{name}: {warning}".replace("%", "%25")
                .replace("\r", "%0D")
                .replace("\n", "%0A")
            )
            print(
                f"::warning::{safe}"
                if os.environ.get("GITHUB_ACTIONS")
                else f"warning: {warning}"
            )
    lines.extend(
        [
            "",
            f"Graph: {document['meta']['publication_count']} publications; generated {document['meta']['generated_at']}.",
        ]
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
