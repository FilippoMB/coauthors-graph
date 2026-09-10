import { edgeWidth } from "./graph-data.js";

export function labelFontSize(isFocal, zoom) {
  const minimum = isFocal ? 14 : 12;
  const maximum = isFocal ? 24 : 20;
  const base = isFocal ? 30 : 26;
  return Math.min(maximum, Math.max(minimum, base * zoom)) / zoom;
}

export function syncGraphAppearance(graph) {
  const zoom = graph.zoom();
  // Cytoscape sizes are graph-space units; keep labels and links legible on screen.
  graph.batch(() => {
    graph.nodes().forEach((node) => {
      node.data({
        font_size: labelFontSize(node.data("is_focal"), zoom),
        label_outline_width: 1.5 / zoom,
        label_margin: 4 / zoom,
      });
    });
    graph.edges().forEach((edge) => {
      edge.data("width", edgeWidth(edge.data("publication_count")) / zoom);
    });
  });
}
