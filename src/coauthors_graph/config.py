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
    name_overrides: dict[str, str]
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
    name_overrides = _string_mapping(raw.get("name_overrides", {}), "name_overrides")
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
        name_overrides=name_overrides,
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
