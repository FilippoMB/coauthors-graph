"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when the graph configuration is invalid."""


@dataclass(frozen=True)
class Config:
    author_id: str
    semantic_scholar_author_id: str
    minimum_publication_year: int
    name_overrides: dict[str, str]
    author_id_overrides: dict[str, str]
    excluded_publication_ids: tuple[str, ...]
    duplicate_groups: tuple[tuple[str, ...], ...]
    community_algorithm: str
    community_resolution: float
    layout_seed: int


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"Configuration file not found: {config_path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"Invalid JSON in {config_path}: {error.msg}") from error

    if not isinstance(raw, dict):
        raise ConfigError("Configuration must be a JSON object")

    author_id = _required_string(raw, "author_id")
    semantic_scholar_author_id = _required_string(raw, "semantic_scholar_author_id")
    if not semantic_scholar_author_id.isdigit():
        raise ConfigError("semantic_scholar_author_id must contain only digits")
    minimum_publication_year = raw.get("minimum_publication_year", 2013)
    if (
        not isinstance(minimum_publication_year, int)
        or isinstance(minimum_publication_year, bool)
        or minimum_publication_year < 0
    ):
        raise ConfigError("minimum_publication_year must be a non-negative integer")

    name_overrides = _string_mapping(raw.get("name_overrides", {}), "name_overrides")
    author_id_overrides = _string_mapping(
        raw.get("author_id_overrides", {}), "author_id_overrides"
    )
    if any(
        not source_id.removeprefix("s2:").isdigit() for source_id in author_id_overrides
    ):
        raise ConfigError(
            "author_id_overrides keys must be numeric Semantic Scholar author IDs"
        )
    excluded_publication_ids = _string_list(
        raw.get("excluded_publication_ids", []), "excluded_publication_ids"
    )
    duplicate_groups = _duplicate_groups(raw.get("duplicate_groups", []))
    algorithm = raw.get("community_algorithm", "greedy_modularity")
    if algorithm not in {"greedy_modularity", "louvain"}:
        raise ConfigError(
            "community_algorithm must be 'greedy_modularity' or 'louvain'"
        )

    resolution = raw.get("community_resolution", 1.5)
    if not isinstance(resolution, (int, float)) or isinstance(resolution, bool):
        raise ConfigError("community_resolution must be a number")
    if resolution <= 0:
        raise ConfigError("community_resolution must be greater than zero")

    layout_seed = raw.get("layout_seed", 42)
    if not isinstance(layout_seed, int) or isinstance(layout_seed, bool):
        raise ConfigError("layout_seed must be an integer")

    return Config(
        author_id=author_id,
        semantic_scholar_author_id=semantic_scholar_author_id,
        minimum_publication_year=minimum_publication_year,
        name_overrides=name_overrides,
        author_id_overrides=author_id_overrides,
        excluded_publication_ids=excluded_publication_ids,
        duplicate_groups=duplicate_groups,
        community_algorithm=algorithm,
        community_resolution=float(resolution),
        layout_seed=layout_seed,
    )


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _string_mapping(value: Any, key: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be an object")
    if not all(
        isinstance(item_key, str)
        and item_key.strip()
        and isinstance(item_value, str)
        and item_value.strip()
        for item_key, item_value in value.items()
    ):
        raise ConfigError(f"{key} keys and values must be non-empty strings")
    return {
        item_key.strip(): item_value.strip() for item_key, item_value in value.items()
    }


def _string_list(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigError(f"{key} must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def _duplicate_groups(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise ConfigError("duplicate_groups must be an array")

    groups: list[tuple[str, ...]] = []
    for group in value:
        if (
            not isinstance(group, list)
            or len(group) < 2
            or not all(isinstance(item, str) and item.strip() for item in group)
        ):
            raise ConfigError(
                "each duplicate_groups entry must contain at least two non-empty strings"
            )
        groups.append(tuple(item.strip() for item in group))
    return tuple(groups)
