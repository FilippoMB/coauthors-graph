# Co-author network

A modern, interactive view of [Filippo Maria Bianchi's](https://dblp.org/pid/139/5968.html) research collaborations, built from DBLP and published as a static GitHub Pages site.

**Live site:** [filippomb.github.io/coauthors-graph](https://filippomb.github.io/coauthors-graph/)

The graph uses color for collaboration communities, node size for publication frequency, and edge width for the number of papers shared by each author pair. The focal author is the star-shaped node. Hover to isolate a neighborhood, click an author to inspect shared publications, drag nodes to explore, or use **Reset layout** to restore the generated positions and viewport.

## How it works

The project is split into two deliberately small parts:

1. The Python package in `src/coauthors_graph` downloads the official DBLP person XML, validates it, constructs a weighted NetworkX graph, detects communities, computes a deterministic layout, and writes versioned JSON.
2. The Vite/Cytoscape.js frontend in `web` renders that JSON as a responsive, accessible static site with adaptive light and dark themes.

Authors are keyed by their stable DBLP PIDs rather than abbreviated names. Journal articles, conference papers, and preprints are treated equally. Books and edited proceedings are not included.

## Local development

Python 3.12+ and Node.js 24 are recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip -e ".[test]"
python -m coauthors_graph --config config.json --output web/public/data/graph.json

cd web
npm ci
npm run dev
```

Vite prints the local URL for the development site. Regenerate `web/public/data/graph.json` whenever you want to pull the latest DBLP records.

Run all automated checks with:

```bash
python -m pytest
python -m ruff check src tests automation
python -m ruff format --check src tests automation
npm --prefix web test
npm --prefix web run build
```

## Configuration

`config.json` contains the graph's stable inputs:

```json
{
  "author_id": "139/5968",
  "name_overrides": {
    "191/9382": "Michael Kampffmeyer",
    "98/256": "Roland Olsson"
  },
  "community_algorithm": "greedy_modularity",
  "community_resolution": 1.5,
  "layout_seed": 42
}
```

- `author_id` is the DBLP PID used for the person export.
- `name_overrides` adjusts display names by stable PID without changing identity.
- `community_algorithm` accepts `greedy_modularity` or `louvain`.
- `community_resolution` controls how finely collaboration communities are divided.
- `layout_seed` makes an unchanged graph render in the same positions.

## Automatic publishing

`.github/workflows/pages.yml` rebuilds and deploys the site:

- after a push to `main`;
- when manually dispatched from the Actions tab;
- every Monday at 06:17 in the `Europe/Oslo` timezone.

Every scheduled run first updates `automation/heartbeat.json` and pushes one bot commit with `[skip ci]`. The commit provides repository activity so GitHub does not disable the schedule after 60 inactive days, while the skip annotation prevents a recursive workflow run. Graph JSON and Vite build output are never committed.

Manual runs normally rebuild without a commit. The optional `record_heartbeat` input exercises the same heartbeat path on demand, which is useful when verifying permissions after changing repository settings.

If DBLP, a test, or the build fails, the workflow does not deploy and the previous successful Pages version remains online. The website displays the generation date of the last successful graph.

### First deployment

1. Open **Settings → Pages** in the GitHub repository.
2. Set **Build and deployment → Source** to **GitHub Actions**.
3. Open **Actions → Refresh and deploy co-author graph** and run the workflow once.
4. Confirm the deployment at the live-site URL above.

The workflow needs `contents: write`, `pages: write`, and `id-token: write`. If `main` has branch protection, allow `github-actions[bot]` to update `automation/heartbeat.json`; otherwise the weekly heartbeat step will fail before the build.

## Data source

Publication metadata comes from the [official DBLP person export](https://dblp.org/faq/How%2Bcan%2BI%2Bfetch%2Ball%2Bpublications%2Bof%2Bone%2Bspecific%2Bauthor). DBLP metadata is released as open data under CC0 1.0.
