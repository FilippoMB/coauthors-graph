import { describe, expect, it } from "vitest";

import {
  communityColor,
  edgeWidth,
  labeledNodeIds,
  nodeSize,
  publicationsForNode,
  resolveTheme,
  validateGraphData,
} from "../src/graph-data.js";

const data = {
  meta: { schema_version: 1, focal_author_id: "a" },
  nodes: [
    { id: "a", label: "Alice", is_focal: true, publication_count: 10 },
    { id: "b", label: "Bob", is_focal: false, publication_count: 3 },
    { id: "c", label: "Carol", is_focal: false, publication_count: 1 },
  ],
  edges: [
    { source: "a", target: "b", publication_ids: ["p1", "p2"] },
    { source: "b", target: "c", publication_ids: ["p2"] },
  ],
  publications: [
    { id: "p1", url: "https://dblp.org/rec/p1", title: "One" },
    { id: "p2", url: "https://dblp.org/rec/p2", title: "Two" },
  ],
};

describe("graph data", () => {
  it("validates the supported schema and DBLP links", () => {
    expect(validateGraphData(data)).toBe(data);
    expect(() => validateGraphData({ ...data, meta: { schema_version: 2 } })).toThrow(
      "Unsupported graph data version",
    );
    expect(() =>
      validateGraphData({
        ...data,
        publications: [{ id: "bad", url: "javascript:alert(1)" }],
      }),
    ).toThrow("unsafe publication link");
  });

  it("scales visual weight monotonically and clamps extremes", () => {
    expect(nodeSize(1)).toBeGreaterThanOrEqual(20);
    expect(nodeSize(10)).toBeGreaterThan(nodeSize(1));
    expect(nodeSize(10000)).toBe(54);
    expect(nodeSize(1, true)).toBe(68);
    expect(edgeWidth(10)).toBeGreaterThan(edgeWidth(1));
    expect(edgeWidth(10000)).toBe(8);
  });

  it("labels the focal author and strongest collaborators", () => {
    const labels = labeledNodeIds(data.nodes, 1);
    expect([...labels]).toEqual(["a", "b"]);
  });

  it("returns publications shared with the focal author", () => {
    expect(publicationsForNode(data, "b").map((item) => item.id)).toEqual(["p1", "p2"]);
    expect(publicationsForNode(data, "c")).toEqual([]);
    expect(publicationsForNode(data, "a")).toHaveLength(2);
  });

  it("resolves adaptive themes and theme-specific colors", () => {
    expect(resolveTheme(undefined, true)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
    expect(communityColor(2, "dark")).not.toBe(communityColor(2, "light"));
  });
});
