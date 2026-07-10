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
  if (value.meta?.schema_version !== 1) {
    throw new Error("Unsupported graph data version.");
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
    value.edges.some(
      (edge) => !nodeIds.has(edge.source) || !nodeIds.has(edge.target),
    )
  ) {
    throw new Error("Graph data contains an edge with an unknown author.");
  }
  if (
    value.publications.some(
      (publication) =>
        typeof publication.url !== "string" ||
        !publication.url.startsWith("https://dblp.org/rec/"),
    )
  ) {
    throw new Error("Graph data contains an unsafe publication link.");
  }
  return value;
}

export function nodeSize(publicationCount, isFocal = false) {
  if (isFocal) {
    return 74;
  }
  const count = Math.max(0, Number(publicationCount) || 0);
  return Math.min(60, Math.max(24, 19 + 7.5 * Math.log2(1 + count)));
}

export function edgeWidth(publicationCount) {
  const count = Math.max(0, Number(publicationCount) || 0);
  return Math.min(8, Math.max(1, 0.75 + 1.2 * Math.sqrt(count)));
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
