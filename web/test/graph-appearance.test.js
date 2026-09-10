import cytoscape from "cytoscape";
import { describe, expect, it } from "vitest";

import { labelFontSize, syncGraphAppearance } from "../src/graph-appearance.js";
import { edgeWidth } from "../src/graph-data.js";

describe("zoom-aware graph appearance", () => {
  it.each([0.04, 0.12, 0.2, 0.5, 1, 3.2])(
    "keeps every label readable at zoom %s",
    (zoom) => {
      const coauthorPixels = labelFontSize(false, zoom) * zoom;
      const focalPixels = labelFontSize(true, zoom) * zoom;
      expect(coauthorPixels).toBeGreaterThanOrEqual(12);
      expect(coauthorPixels).toBeLessThanOrEqual(20);
      expect(focalPixels).toBeGreaterThan(coauthorPixels);
      expect(focalPixels).toBeLessThanOrEqual(24);
    },
  );

  it("preserves visible edge-width differences during zoom and reset", () => {
    const graph = cytoscape({
      headless: true,
      elements: [
        { data: { id: "a", is_focal: true } },
        { data: { id: "b", is_focal: false } },
        { data: { id: "c", is_focal: false } },
        { data: { id: "ab", source: "a", target: "b", publication_count: 1 } },
        { data: { id: "ac", source: "a", target: "c", publication_count: 20 } },
      ],
    });
    graph.on("zoom", () => syncGraphAppearance(graph));
    for (const zoom of [0.2, 1, 3.2, 0.2]) {
      graph.zoom(zoom);
      for (const edge of graph.edges()) {
        expect(edge.data("width") * zoom).toBeCloseTo(edgeWidth(edge.data("publication_count")));
      }
      expect(graph.getElementById("ac").data("width")).toBeGreaterThan(
        5 * graph.getElementById("ab").data("width"),
      );
      expect(graph.getElementById("b").data("font_size") * zoom).toBeGreaterThanOrEqual(12);
    }
    graph.destroy();
  });
});
