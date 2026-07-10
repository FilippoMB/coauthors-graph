import { originalNodePositions } from "./graph-data.js";

export function restoreGeneratedLayout(graph, nodes, animate = true) {
  const originalPositions = originalNodePositions(nodes);
  graph
    .layout({
      name: "preset",
      positions: (node) => originalPositions.get(node.id()),
      fit: true,
      padding: 128,
      animate,
      animationDuration: animate ? 680 : 0,
      animationEasing: "ease-in-out-cubic",
    })
    .run();
}
