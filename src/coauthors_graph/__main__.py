"""Command-line entry point for graph generation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .config import ConfigError, load_config
from .dblp import DblpError, fetch_person_xml, parse_person_xml
from .graph import GraphError, build_graph_document
from .merge import MergeError, combine_profiles
from .semantic_scholar import SemanticScholarError, fetch_author_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a static co-author graph from DBLP and Semantic Scholar."
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
    return parser


def generate(config_path: str | Path, output_path: str | Path) -> Path:
    config = load_config(config_path)
    xml_data = fetch_person_xml(config.author_id)
    dblp_profile = parse_person_xml(xml_data, config.author_id)
    semantic_scholar_profile = fetch_author_profile(
        config.semantic_scholar_author_id,
        api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
    )
    profile = combine_profiles(dblp_profile, semantic_scholar_profile, config)
    document = build_graph_document(profile, config)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        destination = generate(args.config, args.output)
    except (
        ConfigError,
        DblpError,
        SemanticScholarError,
        MergeError,
        GraphError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote co-author graph data to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
