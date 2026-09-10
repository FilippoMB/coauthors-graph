# Co-author network

A modern, interactive view of [Filippo Maria Bianchi's](https://dblp.org/pid/139/5968.html) research collaborations, built from DBLP, Semantic Scholar, and arXiv and published as a static GitHub Pages site.

**Live site:** [filippomb.github.io/coauthors-graph](https://filippomb.github.io/coauthors-graph/)

The graph uses color for collaboration communities, node size for publication frequency, and edge width for the number of works shared by each author pair. The focal author is the large white node. Node labels use initials for clarity; hover or select a node to see the full name. Click an author to inspect shared publications, drag nodes to explore, or use **Reset layout** to restore the generated positions and viewport.

Labels stay at least 12 screen pixels tall when zoomed out. Link widths remain visible at every zoom level (0.65–4.6 screen pixels, logarithmically scaled by shared papers); more frequent collaborations are also higher contrast.

## How it works

The project is split into two deliberately small parts:

1. The Python package in `src/coauthors_graph` independently refreshes DBLP, Semantic Scholar, and arXiv, reconciles contributor identities, removes duplicate preprint/published records, constructs a weighted NetworkX graph, detects communities, computes a deterministic layout, and writes schema-v3 JSON plus a durable source snapshot.
2. The Vite/Cytoscape.js frontend in `web` renders that JSON as a responsive, accessible static site with adaptive light and dark themes.

DBLP PIDs remain the primary author identities. Semantic Scholar contributors are mapped by the focal IDs, explicit overrides, or unambiguous normalized names; genuinely unmatched contributors retain stable `s2:` IDs. All scholarly outputs from 2013 onward contribute equally, including articles, conference papers, preprints, books, chapters, datasets, theses, and editor-only proceedings. Co-editors therefore appear as collaborators.

Published versions replace matching arXiv preprints. Matching uses DOI, arXiv and source identifiers first, then conservative normalized-title, year, and contributor-overlap checks. Fuzzy title matching is limited to preprint/formal candidates, so similar conference and journal extensions remain distinct. Standalone preprints are displayed with the venue `Arxiv`.

Publication details preserve the selected version's original author order, including when a published version replaces a preprint. DBLP bylines use its author/editor signature ordinals, not database-ID or alphabetical order; malformed ordering metadata is rejected rather than guessed.

DBLP's supported SPARQL API is the primary endpoint; XML is a fallback. Direct arXiv discovery combines the ORCID feed with a paginated author-name search, so newly announced papers need not wait for other indexes. The clients validate responses, bound retries and total source time, honor `Retry-After`, and space arXiv requests by at least three seconds on a single connection. Missing Semantic Scholar contributor IDs receive deterministic `provisional:` identities, resolved to known authors when unambiguous. Ambiguous identities remain separate and can be explicitly overridden.

Each deployment includes `data/source-state.json` (state version 1), containing source snapshots, identity mappings, freshness timestamps, and the last valid graph. The next run restores it from Pages. Unavailable sources reuse saved data; invalid records retain their previous versions; omitted records are not silently deleted. When all sources fail, the graph and its generation timestamp stay unchanged. The expandable **Sources** panel separately shows the last check, each source's last complete fetch, and whether it is fresh, partial, cached, or unavailable.

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

The original CLI automatically reuses the sibling `source-state.json`, or bootstraps from an existing graph when no snapshot exists. To reproduce the deployed state explicitly:

```bash
python -m automation.restore_state .refresh-input
python -m coauthors_graph --config config.json \
  --state-input .refresh-input/source-state.json \
  --state-output web/public/data/source-state.json \
  --output web/public/data/graph.json
```

Use `--bootstrap-graph path/to/graph.json` for a first migration from a validated v2/v3 graph. Explicitly supplied missing or corrupt state is an error, not permission to start over. The graph and snapshot are validated before writing; Pages publishes them together. Snapshot data is public bibliographic metadata only; never place API keys in configuration or snapshots.

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
  "arxiv_orcid": "0000-0002-7145-3846",
  "arxiv_author_names": ["Filippo Maria Bianchi"],
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

- `author_id` is the DBLP PID used by the query API and XML fallback.
- `semantic_scholar_author_id` is the supplemental Semantic Scholar author ID.
- `arxiv_orcid` is the ORCID linked to the author's arXiv account; `arxiv_author_names` supplies the names used for discovery and contributor validation.
- `minimum_publication_year` excludes earlier records before identity reconciliation and graph construction.
- `name_overrides` adjusts display names by stable PID without changing identity.
- `author_id_overrides` maps ambiguous contributor IDs to DBLP PIDs. Keys may be raw Semantic Scholar IDs, `s2:` IDs, or `provisional:` IDs; values are DBLP PIDs.
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

Every scheduled run first updates `automation/heartbeat.json` and pushes one bot commit with `[skip ci]`. The commit provides repository activity so GitHub does not disable the schedule after 60 inactive days, while the skip annotation prevents a recursive workflow run. The workflow run ID makes reruns idempotent: the same or an older run does not create another heartbeat. Graph JSON, source snapshots, and Vite build output are never committed.

Manual runs normally rebuild without a commit. The optional `record_heartbeat` input exercises the same heartbeat path on demand, which is useful when verifying permissions after changing repository settings.

An individual source outage no longer blocks updates from healthy sources. Safe degraded updates are deployed with visible source status and Actions warnings. All-source outages can publish check/status information, but cannot advance the graph's generation timestamp. Invalid saved state, failed tests, unexpected implementation errors, or build failures stop deployment and leave the previous Pages version online. The heartbeat is committed before dependency-sensitive steps. Runs are serialized and have bounded timeouts; the Actions summary reports accepted, rejected, retained, and newly seen source records (before cross-source deduplication).

For more reliable scheduled requests, add an optional repository Actions secret named `SEMANTIC_SCHOLAR_API_KEY`. No secret is required for the website or for DBLP.

### Deployment and recovery

1. Open **Settings → Pages** in the GitHub repository.
2. Set **Build and deployment → Source** to **GitHub Actions**.
3. Open **Actions → Refresh and deploy co-author graph** and run the workflow once.
4. Confirm the deployment at the live-site URL above.

This repository's upgrade automatically imports the existing schema-v2 deployment when the first source snapshot is absent. Once migrated, a missing or corrupt snapshot stops the workflow to avoid losing recovery history. For a genuinely new fork with no Pages deployment, first generate a local snapshot and arrange its initial deployment; the production restore step intentionally requires an existing baseline. A failed Pages build never replaces the current durable snapshot.

The workflow needs `contents: write`, `pages: write`, and `id-token: write`. If `main` has branch protection, allow `github-actions[bot]` to update `automation/heartbeat.json`; otherwise the weekly heartbeat step will fail before the build.

## Troubleshooting

- A `429` from Semantic Scholar means the shared unauthenticated pool is busy. The next weekly run retries automatically; healthy sources continue updating and the saved snapshot remains usable. An optional API key can improve availability.
- A DBLP HTML challenge is an unavailable XML endpoint, not malformed publication data. The supported query API is tried first; if both endpoints fail, the previous DBLP snapshot is retained.
- A **Partial update** means invalid/omitted records or incomplete discovery were detected. Previously collected records are preserved; the Actions log explains the affected source. A timestamp for a complete source fetch does not imply every retained historical record was seen again.
- **Last checked** is not a successful graph refresh. If every source is down, the original graph generation timestamp remains unchanged. Source-status dates reveal persistent staleness.
- An ambiguous supplemental author remains a separate `s2:` node by design. Add a narrow `author_id_overrides` entry only after verifying the identity.
- Use `excluded_publication_ids` for a source record attributed to the wrong author.
- Use `duplicate_groups` only for verified versions that automatic matching intentionally leaves separate. Groups with fewer than two currently available records are harmless no-ops, so a future source consolidation cannot permanently stop weekly refreshes.
- The frontend reads v2 and v3 during migration; new generators emit v3. Invalid-source-health errors require regenerating the local graph and snapshot together.
- Recovery is automatic for transient failures, not a guarantee against permanent API changes. Review the Actions failure log if a source remains unavailable over multiple weeks. Do not delete the deployed snapshot to suppress an error.

## Data sources

DBLP remains primary through its [official public query API](https://blog.dblp.org/2024/09/09/introducing-our-public-sparql-query-service/), with the person XML export as fallback. [Semantic Scholar's supported Academic Graph API](https://www.semanticscholar.org/product/api) supplies works absent from DBLP. Direct discovery uses [arXiv's public API](https://info.arxiv.org/help/api/user-manual.html) and [ORCID-linked feeds](https://info.arxiv.org/help/ir.html). Thank you to arXiv for use of its open access interoperability. Only descriptive metadata is stored; PDFs are not mirrored. Google Scholar remains a manual validation reference, not a scheduled data source.
