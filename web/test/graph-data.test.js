import { describe, expect, it } from "vitest";

import {
  communityColor,
  edgeWidth,
  isSafePublicationUrl,
  nodeDisplayLabel,
  nodeSize,
  originalNodePositions,
  publicationsForNode,
  resolveTheme,
  validateGraphData,
} from "../src/graph-data.js";

const data = {
  meta: { schema_version: 2, focal_author_id: "a" },
  nodes: [
    {
      id: "a",
      label: "Alice Maria Example",
      short_label: "A. M. Example",
      is_focal: true,
      publication_count: 10,
    },
    {
      id: "b",
      label: "Bob Builder",
      short_label: "B. Builder",
      is_focal: false,
      publication_count: 3,
    },
    {
      id: "c",
      label: "Carol Researcher",
      short_label: "C. Researcher",
      is_focal: false,
      publication_count: 1,
    },
  ],
  edges: [
    { source: "a", target: "b", publication_ids: ["p1", "p2"] },
    { source: "b", target: "c", publication_ids: ["p2"] },
  ],
  publications: [
    {
      id: "p1",
      url: "https://dblp.org/rec/p1",
      title: "One",
      source: "dblp",
      record_type: "article",
      provenance: ["dblp"],
      external_ids: { DBLP: ["p1"] },
      author_ids: ["a", "b"],
    },
    {
      id: "p2",
      url: "https://doi.org/10.1000/example",
      title: "Two",
      source: "semantic_scholar",
      record_type: "article",
      provenance: ["semantic_scholar"],
      external_ids: { DOI: ["10.1000/example"] },
      author_ids: ["a", "b", "c"],
    },
  ],
};

describe("graph data", () => {
  it("validates schema-v2 data and rejects stale or unsafe metadata", () => {
    expect(validateGraphData(data)).toBe(data);
    expect(() => validateGraphData({ ...data, meta: { schema_version: 1 } })).toThrow(
      "Unsupported graph data version",
    );
    expect(() =>
      validateGraphData({
        ...data,
        publications: [
          { ...data.publications[0], url: "javascript:alert(1)" },
          data.publications[1],
        ],
      }),
    ).toThrow("invalid publication metadata");
  });

  it("allows only exact HTTPS publication providers and paths", () => {
    for (const url of [
      "https://dblp.org/rec/journals/example/Paper.html",
      "https://doi.org/10.1000/example",
      "https://arxiv.org/abs/2401.01234",
      "https://www.semanticscholar.org/paper/abc123",
    ]) {
      expect(isSafePublicationUrl(url)).toBe(true);
    }
    for (const url of [
      "http://doi.org/10.1000/example",
      "javascript:alert(1)",
      "https://doi.org.evil.example/10.1000/example",
      "https://dblp.org/pid/01/1",
      "https://user@arxiv.org/abs/2401.01234",
      "https://arxiv.org/abs/",
    ]) {
      expect(isSafePublicationUrl(url)).toBe(false);
    }
  });

  it("uses initials on nodes without changing the full author name", () => {
    expect(nodeDisplayLabel(data.nodes[0])).toBe("A. M. Example");
    expect(data.nodes[0].label).toBe("Alice Maria Example");
  });

  it("scales visual weight monotonically and clamps extremes", () => {
    expect(nodeSize(1)).toBeGreaterThanOrEqual(24);
    expect(nodeSize(10)).toBeGreaterThan(nodeSize(1));
    expect(nodeSize(10000)).toBe(60);
    expect(nodeSize(1, true)).toBe(84);
    expect(edgeWidth(10)).toBeGreaterThan(edgeWidth(1));
    expect(edgeWidth(10000)).toBe(8);
  });

  it("returns publications shared with the focal author", () => {
    expect(publicationsForNode(data, "b").map((item) => item.id)).toEqual(["p1", "p2"]);
    expect(publicationsForNode(data, "c")).toEqual([]);
    expect(publicationsForNode(data, "a")).toHaveLength(2);
  });

  it("restores each node to its generated position", () => {
    const positions = originalNodePositions([
      { id: "a", x: 12.5, y: -4 },
      { id: "b", x: 7, y: 9 },
    ]);
    expect(positions.get("a")).toEqual({ x: 12.5, y: -4 });
    expect(positions.get("b")).toEqual({ x: 7, y: 9 });
  });

  it("resolves adaptive themes and theme-specific colors", () => {
    expect(resolveTheme(undefined, true)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
    expect(communityColor(2, "dark")).not.toBe(communityColor(2, "light"));
  });
});
