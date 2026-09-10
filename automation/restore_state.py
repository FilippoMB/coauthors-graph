"""Restore durable data from this repository's current Pages deployment."""

import argparse
from pathlib import Path

import requests

from coauthors_graph.config import load_config
from coauthors_graph.http import retrying_session
from coauthors_graph.state import StateError, bootstrap_state, load_state, write_json


PAGES_DATA = "https://filippomb.github.io/coauthors-graph/data"


def restore(destination: Path, config_path: str = "config.json") -> Path:
    config = load_config(config_path)
    with retrying_session() as session:
        response = session.get(
            f"{PAGES_DATA}/source-state.json",
            headers={"Cache-Control": "no-cache"},
            timeout=(5, 30),
        )
        if response.status_code == 404:
            response = session.get(
                f"{PAGES_DATA}/graph.json",
                headers={"Cache-Control": "no-cache"},
                timeout=(5, 30),
            )
            response.raise_for_status()
            graph = response.json()
            if graph.get("meta", {}).get("schema_version") != 2:
                raise StateError(
                    "A migrated deployment is missing source-state.json; refusing to overwrite its state"
                )
            state = bootstrap_state(graph, config.author_id)
        else:
            response.raise_for_status()
            state = response.json()
        path = write_json(destination / "source-state.json", state)
        load_state(path, config.author_id)
        return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        print(f"Restored {restore(args.destination)}")
    except (requests.RequestException, ValueError, OSError) as error:
        print(f"Cannot safely restore the previous deployment: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
