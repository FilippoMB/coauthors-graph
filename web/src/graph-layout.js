import { originalNodePositions } from "./graph-data.js";

export function viewportPadding(width) {
  return width < 600 ? 32 : 72;
}

export function restoreGeneratedLayout(graph, nodes, animate = true) {
  graph.resize();
  const originalPositions = originalNodePositions(nodes);
  graph
    .layout({
      name: "preset",
      positions: (node) => originalPositions.get(node.id()),
      fit: true,
      padding: viewportPadding(graph.width()),
      animate,
      animationDuration: animate ? 680 : 0,
      animationEasing: "ease-in-out-cubic",
    })
    .run();
}
