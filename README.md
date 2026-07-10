# Co-author network

A modern, interactive view of [Filippo Maria Bianchi's](https://dblp.org/pid/139/5968.html) research collaborations, built from DBLP plus Semantic Scholar and published as a static GitHub Pages site.

**Live site:** [filippomb.github.io/coauthors-graph](https://filippomb.github.io/coauthors-graph/)

The graph uses color for collaboration communities, node size for publication frequency, and edge width for the number of works shared by each author pair. The focal author is the star-shaped node. Node labels use initials for clarity; hover or select a node to see the full name. Click an author to inspect shared publications, drag nodes to explore, or use **Reset layout** to restore the generated positions and viewport.

## How it works

The project is split into two deliberately small parts:

1. The Python package in `src/coauthors_graph` downloads DBLP and Semantic Scholar profiles, reconciles contributor identities, removes duplicate preprint/published records, constructs a weighted NetworkX graph, detects communities, computes a deterministic layout, and writes versioned JSON.
2. The Vite/Cytoscape.js frontend in `web` renders that JSON as a responsive, accessible static site with adaptive light and dark themes.

DBLP PIDs remain the primary author identities. Semantic Scholar contributors are mapped by the focal IDs, explicit overrides, or unambiguous normalized names; genuinely unmatched contributors retain stable `s2:` IDs. All scholarly outputs from 2013 onward contribute equally, including articles, conference papers, preprints, books, chapters, datasets, theses, and editor-only proceedings. Co-editors therefore appear as collaborators.

Published versions replace matching arXiv preprints. Matching uses DOI, arXiv and source identifiers first, then conservative normalized-title, year, and contributor-overlap checks. Fuzzy title matching is limited to preprint/formal candidates, so similar conference and journal extensions remain distinct. Standalone preprints are displayed with the venue `Arxiv`.

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

Vite prints the local URL for the development site. Regenerate `web/public/data/graph.json` whenever you want to pull the latest source records. The public Semantic Scholar API works without credentials, but setting `SEMANTIC_SCHOLAR_API_KEY` to a free API key gives the unattended refresh a dedicated rate limit:

```bash
export SEMANTIC_SCHOLAR_API_KEY="your-api-key"
```

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
  "semantic_scholar_author_id": "14553624",
  "minimum_publication_year": 2013,
  "name_overrides": {
    "191/9382": "Michael Kampffmeyer",
    "98/256": "Roland Olsson"
  },
  "author_id_overrides": {},
  "excluded_publication_ids": [],
  "duplicate_groups": [
    [
      "arxiv:1805.03473",
      "doi:10.1016/j.patcog.2019.106973"
    ],
    [
      "arxiv:1907.00481",
      "dblp:conf/icml/BianchiGA20"
    ],
    [
      "arxiv:2501.09821",
      "dblp:journals/tmlr/CastellanaB26"
    ],
    [
      "s2:e284ae76d27f481c758c748f4e67313eded3d621",
      "doi:10.1109/tpami.2021.3054830"
    ]
  ],
  "community_algorithm": "greedy_modularity",
  "community_resolution": 1.5,
  "layout_seed": 42
}
```

- `author_id` is the DBLP PID used for the person export.
- `semantic_scholar_author_id` is the supplemental Semantic Scholar author ID.
- `minimum_publication_year` excludes earlier records before identity reconciliation and graph construction.
- `name_overrides` adjusts display names by stable PID without changing identity.
- `author_id_overrides` maps ambiguous Semantic Scholar contributor IDs to DBLP PIDs. Keys may be raw IDs or `s2:` IDs; values are DBLP PIDs.
- `excluded_publication_ids` removes known source errors. Entries may be canonical IDs such as `s2:<paper-id>` or `dblp:<key>`, DOI/arXiv identifiers, or their raw values.
- `duplicate_groups` is an array of identifier arrays. Each group explicitly declares records to merge when a legitimate version changed too much for conservative automatic matching.
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

If DBLP, Semantic Scholar, a test, or the build fails, the workflow does not deploy and the previous successful Pages version remains online. The heartbeat is committed before those dependency-sensitive steps, and the website continues to display the generation date of the last successful graph.

For more reliable scheduled requests, add an optional repository Actions secret named `SEMANTIC_SCHOLAR_API_KEY`. No secret is required for the website or for DBLP.

### First deployment

1. Open **Settings → Pages** in the GitHub repository.
2. Set **Build and deployment → Source** to **GitHub Actions**.
3. Open **Actions → Refresh and deploy co-author graph** and run the workflow once.
4. Confirm the deployment at the live-site URL above.

The workflow needs `contents: write`, `pages: write`, and `id-token: write`. If `main` has branch protection, allow `github-actions[bot]` to update `automation/heartbeat.json`; otherwise the weekly heartbeat step will fail before the build.

## Troubleshooting

- A `429` from Semantic Scholar means the shared unauthenticated pool is busy. Add the optional API-key secret or retry later; bounded automatic retries already honor `Retry-After`.
- An ambiguous supplemental author remains a separate `s2:` node by design. Add a narrow `author_id_overrides` entry only after verifying the identity.
- Use `excluded_publication_ids` for a source record attributed to the wrong author.
- Use `duplicate_groups` only for verified versions that automatic matching intentionally leaves separate. Groups with fewer than two currently available records are harmless no-ops, so a future source consolidation cannot permanently stop weekly refreshes.
- Schema-v2 frontend errors usually mean a stale local `web/public/data/graph.json`; regenerate it before starting Vite.

## Data sources

DBLP remains the primary source through its [official person export](https://dblp.org/faq/How%2Bcan%2BI%2Bfetch%2Ball%2Bpublications%2Bof%2Bone%2Bspecific%2Bauthor); DBLP metadata is released as open data under CC0 1.0. [Semantic Scholar's supported Academic Graph API](https://www.semanticscholar.org/product/api) supplies works absent from DBLP. Google Scholar is useful for manual validation but is not scraped by the scheduled workflow.
