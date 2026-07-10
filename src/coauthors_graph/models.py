"""Shared immutable models for publication metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Author:
    """A contributor identified by a source-stable identifier."""

    pid: str
    name: str


@dataclass(frozen=True, slots=True)
class Publication:
    """A normalized publication record from one or more metadata sources."""

    key: str
    title: str
    year: int
    venue: str
    url: str
    authors: tuple[Author, ...]
    source: str
    record_type: str
    doi: str | None = None
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    is_preprint: bool = False
    external_ids: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    provenance: tuple[str, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PersonProfile:
    """A person's publications as represented by one or more sources."""

    pid: str
    name: str
    source_urls: tuple[str, ...]
    publications: tuple[Publication, ...]
