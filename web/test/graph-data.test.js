import { describe, expect, it } from "vitest";

import {
  communityColor,
  edgeWidth,
  nodeSize,
  originalNodePositions,
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
    expect(nodeSize(1)).toBeGreaterThanOrEqual(24);
    expect(nodeSize(10)).toBeGreaterThan(nodeSize(1));
    expect(nodeSize(10000)).toBe(60);
    expect(nodeSize(1, true)).toBe(74);
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
