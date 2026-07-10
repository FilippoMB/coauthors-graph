"""Reconcile contributor identities and deduplicate multi-source publications."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from difflib import SequenceMatcher
import re
import unicodedata

from .config import Config
from .models import Author, PersonProfile, Publication


TITLE_SIMILARITY_THRESHOLD = 0.90
AUTHOR_OVERLAP_THRESHOLD = 0.80
MAX_PREPRINT_YEAR_DISTANCE = 3


class MergeError(RuntimeError):
    """Raised when source records cannot be reconciled safely."""


def combine_profiles(
    dblp_profile: PersonProfile,
    semantic_scholar_profile: PersonProfile,
    config: Config,
) -> PersonProfile:
    """Return a filtered, identity-reconciled, deduplicated profile."""

    expected_s2_pid = f"s2:{config.semantic_scholar_author_id}"
    if semantic_scholar_profile.pid != expected_s2_pid:
        raise MergeError(
            "Semantic Scholar profile does not match semantic_scholar_author_id"
        )

    dblp_publications = tuple(
        publication
        for publication in dblp_profile.publications
        if _include_publication(publication, config)
    )
    semantic_publications = tuple(
        publication
        for publication in semantic_scholar_profile.publications
        if _include_publication(publication, config)
    )
    if not dblp_publications:
        raise MergeError("No DBLP publications remain after filtering")
    if not semantic_publications:
        raise MergeError("No Semantic Scholar publications remain after filtering")

    resolver = _AuthorResolver(
        replace(dblp_profile, publications=dblp_publications), config
    )
    mapped_semantic = tuple(
        _map_publication_authors(publication, resolver)
        for publication in semantic_publications
    )
    publications = _deduplicate_publications(
        (*dblp_publications, *mapped_semantic),
        config.duplicate_groups,
    )
    if not publications:
        raise MergeError("No publications remain after deduplication")
    if not any(
        any(author.pid == dblp_profile.pid for author in publication.authors)
        for publication in publications
    ):
        raise MergeError("The focal author is absent after source reconciliation")

    return PersonProfile(
        pid=dblp_profile.pid,
        name=dblp_profile.name,
        source_urls=tuple(
            dict.fromkeys(
                (*dblp_profile.source_urls, *semantic_scholar_profile.source_urls)
            )
        ),
        publications=publications,
    )


class _AuthorResolver:
    def __init__(self, dblp_profile: PersonProfile, config: Config) -> None:
        self._focal_s2_pid = f"s2:{config.semantic_scholar_author_id}"
        self._focal_dblp_pid = dblp_profile.pid
        self._aliases: dict[str, Counter[str]] = defaultdict(Counter)
        for publication in dblp_profile.publications:
            for author in publication.authors:
                self._aliases[author.pid][author.name] += 1
        self._aliases[dblp_profile.pid][dblp_profile.name] += 1
        for pid, name in config.name_overrides.items():
            if pid not in self._aliases:
                raise MergeError(
                    f"name_overrides PID {pid!r} is not a retained DBLP author"
                )
            self._aliases[pid][name] += 1

        self._preferred_names = {
            pid: sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]
            for pid, counter in self._aliases.items()
        }
        self._full_index = self._identity_index(_normalized_name)
        self._initials_index = self._identity_index(_initials_signature)
        self._first_initial_index = self._identity_index(_first_initial_signature)

        self._overrides: dict[str, str] = {}
        for source_id, target_pid in config.author_id_overrides.items():
            normalized_source = (
                source_id if source_id.startswith("s2:") else f"s2:{source_id}"
            )
            normalized_target = target_pid.removeprefix("dblp:")
            if normalized_target not in self._aliases:
                raise MergeError(
                    f"author_id_overrides target {target_pid!r} is not a DBLP author"
                )
            self._overrides[normalized_source] = normalized_target

    def resolve(self, author: Author) -> Author:
        pid = self._resolved_pid(author)
        return Author(pid=pid, name=self._preferred_names.get(pid, author.name))

    def _resolved_pid(self, author: Author) -> str:
        if author.pid == self._focal_s2_pid:
            return self._focal_dblp_pid
        if author.pid in self._overrides:
            return self._overrides[author.pid]

        for signature, index in (
            (_normalized_name(author.name), self._full_index),
            (_initials_signature(author.name), self._initials_index),
            (_first_initial_signature(author.name), self._first_initial_index),
        ):
            candidates = index.get(signature, frozenset())
            if len(candidates) == 1:
                return next(iter(candidates))
        return author.pid

    def _identity_index(self, signature_fn) -> dict[str, frozenset[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for pid, aliases in self._aliases.items():
            for alias in aliases:
                signature = signature_fn(alias)
                if signature:
                    index[signature].add(pid)
        return {signature: frozenset(pids) for signature, pids in index.items()}


def _map_publication_authors(
    publication: Publication, resolver: _AuthorResolver
) -> Publication:
    mapped: dict[str, Author] = {}
    for author in publication.authors:
        resolved = resolver.resolve(author)
        mapped.setdefault(resolved.pid, resolved)
    return replace(publication, authors=tuple(mapped.values()))


def _include_publication(publication: Publication, config: Config) -> bool:
    if publication.year < config.minimum_publication_year:
        return False
    identifiers = _publication_tokens(publication)
    return not any(
        _normalize_identifier(identifier) in identifiers
        for identifier in config.excluded_publication_ids
    )


def _deduplicate_publications(
    publications: tuple[Publication, ...],
    duplicate_groups: tuple[tuple[str, ...], ...],
) -> tuple[Publication, ...]:
    ordered = tuple(sorted(publications, key=lambda item: item.key))
    clusters = _DisjointSet(len(ordered))

    formal_indices = [
        index
        for index, publication in enumerate(ordered)
        if not publication.is_preprint
    ]
    preprint_indices = [
        index for index, publication in enumerate(ordered) if publication.is_preprint
    ]

    _cluster_formal_copies(ordered, formal_indices, clusters)
    _cluster_preprint_copies(ordered, preprint_indices, clusters)
    _apply_explicit_groups(ordered, duplicate_groups, clusters)
    _attach_preprints_to_formal_works(ordered, clusters)

    grouped: dict[int, list[Publication]] = defaultdict(list)
    for index, publication in enumerate(ordered):
        grouped[clusters.find(index)].append(publication)

    merged = tuple(
        sorted(
            (_merge_cluster(tuple(group)) for group in grouped.values()),
            key=lambda item: item.key,
        )
    )
    if len({publication.key for publication in merged}) != len(merged):
        raise MergeError("Deduplication produced repeated canonical publication IDs")
    return merged


def _cluster_formal_copies(
    publications: tuple[Publication, ...],
    indices: list[int],
    clusters: "_DisjointSet",
) -> None:
    for position, left_index in enumerate(indices):
        for right_index in indices[position + 1 :]:
            left = publications[left_index]
            right = publications[right_index]
            if _share_formal_identifier(left, right):
                clusters.union(left_index, right_index)

    for position, left_index in enumerate(indices):
        for right_index in indices[position + 1 :]:
            if clusters.find(left_index) == clusters.find(right_index):
                continue
            left = publications[left_index]
            right = publications[right_index]
            if not _are_cross_source_formal_copies(left, right):
                continue
            left_sources = {
                publications[index].source
                for index in clusters.members(left_index)
                if not publications[index].is_preprint
            }
            right_sources = {
                publications[index].source
                for index in clusters.members(right_index)
                if not publications[index].is_preprint
            }
            if left_sources.isdisjoint(right_sources):
                clusters.union(left_index, right_index)


def _cluster_preprint_copies(
    publications: tuple[Publication, ...],
    indices: list[int],
    clusters: "_DisjointSet",
) -> None:
    for position, left_index in enumerate(indices):
        for right_index in indices[position + 1 :]:
            left = publications[left_index]
            right = publications[right_index]
            if _share_preprint_identifier(left, right) or _preprint_copy_match(
                left, right
            ):
                clusters.union(left_index, right_index)


def _apply_explicit_groups(
    publications: tuple[Publication, ...],
    duplicate_groups: tuple[tuple[str, ...], ...],
    clusters: "_DisjointSet",
) -> None:
    tokens_by_index = [_publication_tokens(publication) for publication in publications]
    for group in duplicate_groups:
        matched_indices: list[int] = []
        for raw_identifier in group:
            identifier = _normalize_identifier(raw_identifier)
            matches = [
                index
                for index, tokens in enumerate(tokens_by_index)
                if identifier in tokens
            ]
            matched_indices.extend(matches)
        matched_indices = sorted(set(matched_indices))
        if len(matched_indices) < 2:
            continue
        anchor = matched_indices[0]
        for index in matched_indices[1:]:
            clusters.union(anchor, index)


def _attach_preprints_to_formal_works(
    publications: tuple[Publication, ...], clusters: "_DisjointSet"
) -> None:
    roots = sorted({clusters.find(index) for index in range(len(publications))})
    formal_roots = [
        root
        for root in roots
        if any(not publications[index].is_preprint for index in clusters.members(root))
    ]
    preprint_roots = [
        root
        for root in roots
        if all(publications[index].is_preprint for index in clusters.members(root))
    ]

    for preprint_root in preprint_roots:
        candidates: list[tuple[tuple[float, ...], int]] = []
        for formal_root in formal_roots:
            score = _cluster_match_score(
                publications,
                clusters.members(preprint_root),
                clusters.members(formal_root),
            )
            if score is not None:
                candidates.append((score, formal_root))
        if not candidates:
            continue

        candidates.sort(reverse=True)
        best_score, best_root = candidates[0]
        if len(candidates) > 1 and candidates[1][0] == best_score:
            continue
        clusters.union(preprint_root, best_root)


def _cluster_match_score(
    publications: tuple[Publication, ...],
    preprint_indices: tuple[int, ...],
    formal_indices: tuple[int, ...],
) -> tuple[float, ...] | None:
    scores: list[tuple[float, ...]] = []
    for preprint_index in preprint_indices:
        preprint = publications[preprint_index]
        for formal_index in formal_indices:
            formal = publications[formal_index]
            direct_rank = _preprint_formal_identifier_rank(preprint, formal)
            similarity = _title_similarity(preprint.title, formal.title)
            overlap, matching_authors = _author_overlap(preprint, formal)
            year_distance = abs(preprint.year - formal.year)
            conservative_match = (
                similarity >= TITLE_SIMILARITY_THRESHOLD
                and year_distance <= MAX_PREPRINT_YEAR_DISTANCE
                and overlap >= AUTHOR_OVERLAP_THRESHOLD
                and matching_authors >= 2
            )
            if direct_rank == 0 and not conservative_match:
                continue
            scores.append(
                (
                    float(direct_rank),
                    round(similarity, 12),
                    round(overlap, 12),
                    float(-year_distance),
                )
            )
    return max(scores) if scores else None


def _share_formal_identifier(left: Publication, right: Publication) -> bool:
    left_ids = _formal_identity_tokens(left)
    right_ids = _formal_identity_tokens(right)
    return bool(left_ids & right_ids)


def _share_preprint_identifier(left: Publication, right: Publication) -> bool:
    left_ids = _preprint_identity_tokens(left)
    right_ids = _preprint_identity_tokens(right)
    return bool(left_ids & right_ids)


def _are_cross_source_formal_copies(left: Publication, right: Publication) -> bool:
    if left.source == right.source or _conflicting_dois(left, right):
        return False
    if _normalized_title(left.title) != _normalized_title(right.title):
        return False
    if abs(left.year - right.year) > 1:
        return False
    overlap, matching_authors = _author_overlap(left, right)
    return overlap == 1.0 and matching_authors >= 1


def _preprint_copy_match(left: Publication, right: Publication) -> bool:
    if abs(left.year - right.year) > MAX_PREPRINT_YEAR_DISTANCE:
        return False
    overlap, matching_authors = _author_overlap(left, right)
    return (
        _normalized_title(left.title) == _normalized_title(right.title)
        and overlap >= AUTHOR_OVERLAP_THRESHOLD
        and matching_authors >= 2
    )


def _preprint_formal_identifier_rank(preprint: Publication, formal: Publication) -> int:
    if _formal_identity_tokens(preprint) & _formal_identity_tokens(formal):
        return 3
    if _arxiv_tokens(preprint) & _arxiv_tokens(formal):
        return 2
    return 0


def _formal_identity_tokens(publication: Publication) -> set[str]:
    tokens: set[str] = set()
    if publication.doi:
        tokens.add(f"doi:{_normalize_doi(publication.doi)}")
    if publication.semantic_scholar_id:
        tokens.add(f"s2:{publication.semantic_scholar_id.casefold()}")
    for key, value in publication.external_ids:
        normalized_key = key.casefold()
        if normalized_key == "doi":
            tokens.add(f"doi:{_normalize_doi(value)}")
        elif normalized_key == "semanticscholar":
            tokens.add(f"s2:{value.casefold()}")
        elif normalized_key == "dblp":
            tokens.add(f"dblp:{value.casefold()}")
    return tokens


def _preprint_identity_tokens(publication: Publication) -> set[str]:
    return _formal_identity_tokens(publication) | _arxiv_tokens(publication)


def _arxiv_tokens(publication: Publication) -> set[str]:
    values = []
    if publication.arxiv_id:
        values.append(publication.arxiv_id)
    values.extend(
        value for key, value in publication.external_ids if key.casefold() == "arxiv"
    )
    return {f"arxiv:{_normalize_arxiv_id(value)}" for value in values if value}


def _conflicting_dois(left: Publication, right: Publication) -> bool:
    left_dois = {
        token for token in _formal_identity_tokens(left) if token.startswith("doi:")
    }
    right_dois = {
        token for token in _formal_identity_tokens(right) if token.startswith("doi:")
    }
    return bool(left_dois and right_dois and left_dois.isdisjoint(right_dois))


def _author_overlap(left: Publication, right: Publication) -> tuple[float, int]:
    left_authors = {author.pid for author in left.authors}
    right_authors = {author.pid for author in right.authors}
    matching = len(left_authors & right_authors)
    denominator = max(len(left_authors), len(right_authors), 1)
    return matching / denominator, matching


def _merge_cluster(records: tuple[Publication, ...]) -> Publication:
    representative = min(records, key=_representative_sort_key)
    external_ids = sorted(
        {
            (key, value)
            for record in records
            for key, value in record.external_ids
            if key and value
        },
        key=lambda item: (item[0].casefold(), item[1].casefold()),
    )
    provenance = tuple(
        sorted(
            {source for record in records for source in record.provenance},
            key=lambda source: (source != "dblp", source),
        )
    )
    source_ids = tuple(
        sorted({source_id for record in records for source_id in record.source_ids})
    )
    doi = representative.doi or next(
        (record.doi for record in records if record.doi), None
    )
    arxiv_id = representative.arxiv_id or next(
        (record.arxiv_id for record in records if record.arxiv_id), None
    )
    semantic_scholar_id = representative.semantic_scholar_id or next(
        (
            record.semantic_scholar_id
            for record in records
            if record.semantic_scholar_id
        ),
        None,
    )
    is_preprint = all(record.is_preprint for record in records)

    return replace(
        representative,
        doi=doi,
        arxiv_id=arxiv_id,
        semantic_scholar_id=semantic_scholar_id,
        is_preprint=is_preprint,
        external_ids=tuple(external_ids),
        provenance=provenance,
        source_ids=source_ids,
    )


def _representative_sort_key(publication: Publication) -> tuple[object, ...]:
    source_priority = 0 if publication.source == "dblp" else 1
    richness = sum(
        (
            bool(publication.doi),
            bool(publication.arxiv_id),
            publication.venue not in {"DBLP", "Semantic Scholar", "Arxiv"},
            publication.record_type != "scholarly-output",
        )
    )
    return (publication.is_preprint, source_priority, -richness, publication.key)


def _publication_tokens(publication: Publication) -> set[str]:
    tokens = {
        _normalize_identifier(publication.key),
        *(_normalize_identifier(value) for value in publication.source_ids),
    }
    for key, value in publication.external_ids:
        tokens.add(_normalize_identifier(f"{key}:{value}"))
        tokens.add(_normalize_identifier(value))
    if publication.doi:
        tokens.add(f"doi:{_normalize_doi(publication.doi)}")
        tokens.add(_normalize_doi(publication.doi))
    if publication.arxiv_id:
        normalized_arxiv = _normalize_arxiv_id(publication.arxiv_id)
        tokens.add(f"arxiv:{normalized_arxiv}")
        tokens.add(normalized_arxiv)
    return tokens


def _normalize_identifier(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized.startswith("https://doi.org/"):
        return f"doi:{_normalize_doi(normalized)}"
    if normalized.startswith("https://arxiv.org/abs/"):
        return f"arxiv:{_normalize_arxiv_id(normalized)}"
    return normalized


def _normalize_doi(value: str) -> str:
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    return normalized.rstrip(".,;)")


def _normalize_arxiv_id(value: str) -> str:
    normalized = value.strip().casefold()
    for prefix in (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "arxiv:",
    ):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    return re.sub(r"v\d+$", "", normalized.removesuffix(".pdf"))


def _normalized_title(title: str) -> str:
    return _normalized_words(title)


def _title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, _normalized_title(left), _normalized_title(right)
    ).ratio()


def _normalized_name(name: str) -> str:
    tokens = _name_tokens(name)
    return " ".join(tokens)


def _initials_signature(name: str) -> str:
    tokens = _name_tokens(name)
    if not tokens:
        return ""
    return " ".join([*(token[0] for token in tokens[:-1]), tokens[-1]])


def _first_initial_signature(name: str) -> str:
    tokens = _name_tokens(name)
    if not tokens:
        return ""
    return f"{tokens[0][0]} {tokens[-1]}"


def _name_tokens(name: str) -> list[str]:
    tokens = _normalized_words(name).split()
    if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
        tokens.pop()
    return tokens


def _normalized_words(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " " for character in without_marks
        ).split()
    )


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self._parents = list(range(size))

    def find(self, item: int) -> int:
        parent = self._parents[item]
        if parent != item:
            self._parents[item] = self.find(parent)
        return self._parents[item]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        self._parents[max(left_root, right_root)] = min(left_root, right_root)

    def members(self, item: int) -> tuple[int, ...]:
        root = self.find(item)
        return tuple(
            index for index in range(len(self._parents)) if self.find(index) == root
        )
