"""Command-line entry point for graph generation."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys

from .config import ConfigError, load_config
from .graph import GraphError
from .merge import MergeError
from .refresh import refresh, write_run_summary
from .state import (
    StateError,
    bootstrap_state,
    empty_state,
    load_state,
    read_json,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh a co-author graph from DBLP, Semantic Scholar, and arXiv."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to the JSON configuration file (default: config.json)",
    )
    parser.add_argument(
        "--output",
        default="web/public/data/graph.json",
        help="Destination for the generated graph JSON",
    )
    parser.add_argument("--state-input", help="Previously deployed source-state JSON")
    parser.add_argument(
        "--state-output", help="Destination for the next source-state JSON"
    )
    parser.add_argument(
        "--bootstrap-graph",
        help="Existing v2/v3 graph for the first snapshot migration",
    )
    return parser


def generate(
    config_path: str | Path,
    output_path: str | Path,
    *,
    state_input=None,
    state_output=None,
    bootstrap_graph=None,
) -> Path:
    config = load_config(config_path)
    destination = Path(output_path)
    state_destination = (
        Path(state_output)
        if state_output
        else destination.with_name("source-state.json")
    )
    if state_destination.resolve() == destination.resolve():
        raise StateError("Graph output and state output must be different files")
    if state_input:
        previous = load_state(state_input, config.author_id)
    elif state_destination.exists():
        previous = load_state(state_destination, config.author_id)
    elif bootstrap_graph or destination.exists():
        previous = bootstrap_state(
            read_json(bootstrap_graph or destination), config.author_id
        )
    else:
        previous = empty_state(config.author_id)
    document, state = refresh(config, previous)
    # Everything has been validated before either output is replaced. Deployment
    # publishes these files together; interrupted local runs recover from state.graph.
    write_json(state_destination, state)
    write_json(destination, document)
    write_run_summary(document)
    return destination


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        destination = generate(
            args.config,
            args.output,
            state_input=args.state_input,
            state_output=args.state_output,
            bootstrap_graph=args.bootstrap_graph,
        )
    except (
        ConfigError,
        StateError,
        MergeError,
        GraphError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with Path(summary).open("a", encoding="utf-8") as stream:
                stream.write(
                    "## Publication refresh failed\n\nValidation or generation failed. The previous Pages deployment is unchanged. See the step log for details.\n"
                )
        return 1

    print(f"Wrote co-author graph data to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
