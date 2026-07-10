import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { restoreGeneratedLayout } from "../src/graph-layout.js";


describe("graph layout", () => {
  it("restores dragged nodes to generated positions", () => {
    const nodes = [
      { id: "a", x: 12.5, y: -4 },
      { id: "b", x: 7, y: 9 },
    ];
    const graph = cytoscape({
      headless: true,
      elements: nodes.map((node) => ({ data: { id: node.id } })),
    });
    graph.getElementById("a").position({ x: 100, y: 100 });
    graph.getElementById("b").position({ x: -100, y: -100 });

    restoreGeneratedLayout(graph, nodes, false);

    expect(graph.getElementById("a").position()).toEqual({ x: 12.5, y: -4 });
    expect(graph.getElementById("b").position()).toEqual({ x: 7, y: 9 });
  });
});
