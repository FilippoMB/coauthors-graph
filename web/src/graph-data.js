const LIGHT_COMMUNITIES = [
  "#2563eb",
  "#db2777",
  "#059669",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#dc2626",
  "#4f46e5",
  "#65a30d",
  "#c026d3",
  "#0f766e",
  "#ea580c",
];

const DARK_COMMUNITIES = [
  "#60a5fa",
  "#f472b6",
  "#34d399",
  "#fbbf24",
  "#a78bfa",
  "#22d3ee",
  "#fb7185",
  "#818cf8",
  "#a3e635",
  "#e879f9",
  "#2dd4bf",
  "#fb923c",
];

export function validateGraphData(value) {
  if (!value || typeof value !== "object") {
    throw new Error("Graph data must be an object.");
  }
  if (![2, 3].includes(value.meta?.schema_version)) {
    throw new Error("Unsupported graph data version.");
  }
  if (value.meta.schema_version === 3) {
    const { sources, last_checked_at: checked, generated_at: generated } = value.meta;
    if (
      !Number.isFinite(Date.parse(checked)) || !Number.isFinite(Date.parse(generated)) ||
      !sources || typeof sources !== "object" || Array.isArray(sources) ||
      Object.values(sources).some((source) =>
        !source || !["fresh", "partial", "cached", "unavailable"].includes(source.status) ||
        !Number.isFinite(Date.parse(source.last_attempt_at)) ||
        (source.last_success_at !== null && !Number.isFinite(Date.parse(source.last_success_at))) ||
        ["accepted_count", "rejected_count", "retained_count", "added_count"].some(
          (key) => !Number.isInteger(source[key]) || source[key] < 0,
        ),
      )
    ) {
      throw new Error("Graph data contains invalid source health metadata.");
    }
  }
  for (const collection of ["nodes", "edges", "publications"]) {
    if (!Array.isArray(value[collection])) {
      throw new Error(`Graph data is missing ${collection}.`);
    }
  }

  const nodeIds = new Set(value.nodes.map((node) => node.id));
  if (nodeIds.size !== value.nodes.length || !nodeIds.has(value.meta.focal_author_id)) {
    throw new Error("Graph data contains invalid author identifiers.");
  }
  if (
    value.nodes.some(
      (node) =>
        typeof node.id !== "string" ||
        typeof node.label !== "string" ||
        !node.label.trim() ||
        typeof node.short_label !== "string" ||
        !node.short_label.trim(),
    )
  ) {
    throw new Error("Graph data contains invalid author labels.");
  }

  const publicationIds = new Set(value.publications.map((publication) => publication.id));
  if (publicationIds.size !== value.publications.length) {
    throw new Error("Graph data contains repeated publication identifiers.");
  }
  if (
    value.edges.some(
      (edge) =>
        !nodeIds.has(edge.source) ||
        !nodeIds.has(edge.target) ||
        !Array.isArray(edge.publication_ids) ||
        edge.publication_ids.some((id) => !publicationIds.has(id)),
    )
  ) {
    throw new Error("Graph data contains an invalid edge reference.");
  }
  if (
    value.publications.some(
      (publication) =>
        !isSafePublicationUrl(publication.url) ||
        typeof publication.source !== "string" ||
        !publication.source.trim() ||
        typeof publication.record_type !== "string" ||
        !publication.record_type.trim() ||
        !Array.isArray(publication.provenance) ||
        !publication.external_ids ||
        typeof publication.external_ids !== "object" ||
        Array.isArray(publication.external_ids) ||
        !Array.isArray(publication.author_ids) ||
        publication.author_ids.some((id) => !nodeIds.has(id)) ||
        Object.values(publication.external_ids).some(
          (identifiers) =>
            !Array.isArray(identifiers) ||
            identifiers.some(
              (identifier) => typeof identifier !== "string" || !identifier,
            ),
        ),
    )
  ) {
    throw new Error("Graph data contains invalid publication metadata.");
  }
  return value;
}

export function nodeDisplayLabel(node) {
  return node.short_label;
}

export function isSafePublicationUrl(value) {
  if (typeof value !== "string") {
    return false;
  }

  let url;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    url.search ||
    url.hash
  ) {
    return false;
  }

  const allowedPaths = new Map([
    ["dblp.org", "/rec/"],
    ["doi.org", "/"],
    ["arxiv.org", "/abs/"],
    ["www.semanticscholar.org", "/paper/"],
  ]);
  const pathPrefix = allowedPaths.get(url.hostname);
  return Boolean(
    pathPrefix &&
      url.pathname.startsWith(pathPrefix) &&
      url.pathname.length > pathPrefix.length,
  );
}

export function nodeSize(publicationCount, isFocal = false) {
  if (isFocal) {
    return 84;
  }
  const count = Math.max(0, Number(publicationCount) || 0);
  return Math.min(60, Math.max(24, 19 + 7.5 * Math.log2(1 + count)));
}

export function edgeWidth(publicationCount) {
  const count = Math.max(1, Number(publicationCount) || 1);
  return Math.min(4.6, 0.65 + 0.9 * Math.log2(count));
}

export function edgeOpacity(publicationCount) {
  const count = Math.max(1, Number(publicationCount) || 1);
  return Math.min(0.64, 0.22 + 0.1 * Math.log2(count));
}

export function communityColor(community, theme) {
  const palette = theme === "dark" ? DARK_COMMUNITIES : LIGHT_COMMUNITIES;
  const index = Math.abs(Number(community) || 0) % palette.length;
  return palette[index];
}

export function publicationsForNode(data, nodeId) {
  let publicationIds;
  if (nodeId === data.meta.focal_author_id) {
    publicationIds = new Set(data.publications.map((publication) => publication.id));
  } else {
    const edge = data.edges.find(
      (item) =>
        (item.source === data.meta.focal_author_id && item.target === nodeId) ||
        (item.target === data.meta.focal_author_id && item.source === nodeId),
    );
    publicationIds = new Set(edge?.publication_ids ?? []);
  }
  return data.publications.filter((publication) => publicationIds.has(publication.id));
}

export function originalNodePositions(nodes) {
  return new Map(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
}

export function resolveTheme(storedTheme, prefersDark) {
  if (storedTheme === "light" || storedTheme === "dark") {
    return storedTheme;
  }
  return prefersDark ? "dark" : "light";
}
