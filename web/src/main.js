import cytoscape from "cytoscape";

import {
  communityColor,
  edgeWidth,
  nodeDisplayLabel,
  nodeSize,
  publicationsForNode,
  resolveTheme,
  validateGraphData,
} from "./graph-data.js";
import { restoreGeneratedLayout } from "./graph-layout.js";
import "./styles.css";

const COAUTHOR_LABEL_SIZE = 18;
const FOCAL_AUTHOR_LABEL_SIZE = 21;

const elements = {
  title: document.querySelector("#page-title"),
  summary: document.querySelector("#graph-summary"),
  updatedAt: document.querySelector("#updated-at"),
  loading: document.querySelector("#loading"),
  error: document.querySelector("#error"),
  errorMessage: document.querySelector("#error-message"),
  resetButton: document.querySelector("#reset-button"),
  themeButton: document.querySelector("#theme-button"),
  tooltip: document.querySelector("#tooltip"),
  tooltipName: document.querySelector("#tooltip-name"),
  tooltipCount: document.querySelector("#tooltip-count"),
  details: document.querySelector("#details"),
  detailsClose: document.querySelector("#details-close"),
  detailsName: document.querySelector("#details-name"),
  detailsSummary: document.querySelector("#details-summary"),
  publicationList: document.querySelector("#publication-list"),
};

const mediaTheme = window.matchMedia("(prefers-color-scheme: dark)");
let manualTheme = readStoredTheme();
let activeTheme = resolveTheme(manualTheme, mediaTheme.matches);
let graph;
let graphData;
let selectedNode;

applyDocumentTheme(activeTheme);
void initialize();

async function initialize() {
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}data/graph.json`);
    if (!response.ok) {
      throw new Error(`The graph data request returned ${response.status}.`);
    }
    graphData = validateGraphData(await response.json());
    renderMetadata(graphData);
    graph = createGraph(graphData);
    bindGraphEvents();
    elements.resetButton.addEventListener("click", resetGraph);
    elements.detailsClose.addEventListener("click", clearSelection);
    elements.loading.hidden = true;
  } catch (error) {
    showError(error);
  }
}

function createGraph(data) {
  const nodes = data.nodes.map((node) => ({
    data: {
      ...node,
      display_label: nodeDisplayLabel(node),
      size: nodeSize(node.publication_count, node.is_focal),
      font_size: node.is_focal ? FOCAL_AUTHOR_LABEL_SIZE : COAUTHOR_LABEL_SIZE,
      color: communityColor(node.community, activeTheme),
      label_color: activeTheme === "dark" ? "#e8eef8" : "#172033",
      label_outline: activeTheme === "dark" ? "#07111f" : "#f6f8fc",
      focal_color: "#ffffff",
      focal_border: activeTheme === "dark" ? "#60a5fa" : "#2563eb",
      selection_border: activeTheme === "dark" ? "#ffffff" : "#0f172a",
    },
    position: { x: node.x, y: node.y },
  }));
  const edgeColor = activeTheme === "dark" ? "#91a4bf" : "#64748b";
  const edges = data.edges.map((edge) => ({
    data: {
      ...edge,
      width: edgeWidth(edge.publication_count),
      color: edgeColor,
    },
  }));

  return cytoscape({
    container: document.querySelector("#cy"),
    elements: { nodes, edges },
    layout: { name: "preset", fit: true, padding: 128 },
    minZoom: 0.18,
    maxZoom: 3.2,
    wheelSensitivity: 0.22,
    style: [
      {
        selector: "node",
        style: {
          width: "data(size)",
          height: "data(size)",
          shape: "ellipse",
          "background-color": "data(color)",
          "border-width": 2,
          "border-color": "data(label_outline)",
          label: "data(display_label)",
          color: "data(label_color)",
          "font-family": "Inter, ui-sans-serif, system-ui, sans-serif",
          "font-size": "data(font_size)",
          "font-weight": 700,
          "text-outline-color": "data(label_outline)",
          "text-outline-width": 4,
          "text-valign": "bottom",
          "text-margin-y": 11,
          "text-wrap": "wrap",
          "text-max-width": 150,
          "min-zoomed-font-size": 4,
          "shadow-blur": 18,
          "shadow-color": "data(color)",
          "shadow-opacity": 0.3,
          "shadow-offset-x": 0,
          "shadow-offset-y": 3,
          "overlay-opacity": 0,
          "transition-property": "opacity, border-width, border-color, shadow-opacity",
          "transition-duration": "160ms",
        },
      },
      {
        selector: "node[?is_focal]",
        style: {
          "background-color": "data(focal_color)",
          "border-width": 3,
          "border-color": "data(focal_border)",
          "shadow-blur": 28,
          "shadow-color": "data(focal_border)",
          "shadow-opacity": 0.6,
          "z-index": 10,
        },
      },
      {
        selector: "edge",
        style: {
          width: "data(width)",
          "line-color": "data(color)",
          "curve-style": "bezier",
          opacity: 0.24,
          "overlay-opacity": 0,
          "transition-property": "opacity, line-color",
          "transition-duration": "160ms",
        },
      },
      {
        selector: ".muted",
        style: { opacity: 0.07 },
      },
      {
        selector: "edge.focused",
        style: { opacity: 0.78 },
      },
      {
        selector: "node.selected",
        style: {
          "border-width": 5,
          "border-color": "data(selection_border)",
          "shadow-opacity": 0.75,
          "shadow-blur": 30,
        },
      },
    ],
  });
}

function bindGraphEvents() {
  graph.on("mouseover", "node", (event) => {
    focusNode(event.target, false);
    showTooltip(event.target, event.renderedPosition);
  });
  graph.on("mousemove", "node", (event) => {
    positionTooltip(event.renderedPosition);
  });
  graph.on("mouseout", "node", () => {
    elements.tooltip.hidden = true;
    if (selectedNode) {
      focusNode(selectedNode, true);
    } else {
      clearGraphFocus();
    }
  });
  graph.on("tap", "node", (event) => {
    selectedNode = event.target;
    focusNode(selectedNode, true);
    renderDetails(selectedNode.id());
  });
  graph.on("tap", (event) => {
    if (event.target === graph) {
      clearSelection();
    }
  });
  graph.on("pan zoom drag", () => {
    elements.tooltip.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      clearSelection();
    }
  });
}

function focusNode(node, selected) {
  graph.elements().removeClass("muted focused selected");
  graph.elements().addClass("muted");
  const neighborhood = node.closedNeighborhood();
  neighborhood.removeClass("muted");
  neighborhood.edges().addClass("focused");
  if (selected) {
    node.addClass("selected");
  }
}

function clearGraphFocus() {
  graph?.elements().removeClass("muted focused selected");
}

function clearSelection() {
  selectedNode = undefined;
  clearGraphFocus();
  elements.details.classList.remove("open");
  elements.details.setAttribute("aria-hidden", "true");
}

function renderDetails(nodeId) {
  const node = graphData.nodes.find((item) => item.id === nodeId);
  const publications = publicationsForNode(graphData, nodeId);
  elements.detailsName.textContent = node.label;
  if (node.is_focal) {
    elements.detailsSummary.textContent = `${publications.length} publications in this network`;
  } else {
    const suffix = publications.length === 1 ? "publication" : "publications";
    elements.detailsSummary.textContent = `${publications.length} shared ${suffix} with ${focalAuthor().label}`;
  }

  elements.publicationList.replaceChildren(
    ...publications.map((publication) => publicationItem(publication)),
  );
  elements.details.classList.add("open");
  elements.details.setAttribute("aria-hidden", "false");
}

function publicationItem(publication) {
  const item = document.createElement("li");
  const link = document.createElement("a");
  const title = document.createElement("span");
  const metadata = document.createElement("span");
  const authors = document.createElement("span");

  link.href = publication.url;
  link.target = "_blank";
  link.rel = "noreferrer";
  title.className = "publication-title";
  title.textContent = publication.title;
  metadata.className = "publication-meta";
  metadata.textContent = `${publication.year} · ${publication.venue}`;
  authors.className = "publication-authors";
  authors.textContent = publication.author_ids
    .map((authorId) => graphData.nodes.find((node) => node.id === authorId)?.label)
    .filter(Boolean)
    .join(", ");
  link.append(title, metadata, authors);
  item.append(link);
  return item;
}

function renderMetadata(data) {
  const focal = focalAuthor();
  elements.title.textContent = focal.label;
  document.title = `${focal.label} · Co-author network`;
  elements.summary.textContent = `${data.meta.coauthor_count} co-authors · ${data.meta.publication_count} publications · ${data.meta.year_range[0]}–${data.meta.year_range[1]}`;
  const generatedAt = new Date(data.meta.generated_at);
  elements.updatedAt.textContent = `Updated ${new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(generatedAt)}`;
  elements.updatedAt.title = `Last successful graph generation: ${generatedAt.toLocaleString()}`;
}

function focalAuthor() {
  return graphData.nodes.find((node) => node.id === graphData.meta.focal_author_id);
}

function showTooltip(node, renderedPosition) {
  const count = node.data("publication_count");
  elements.tooltipName.textContent = node.data("label");
  elements.tooltipCount.textContent = `${count} ${count === 1 ? "publication" : "publications"}`;
  elements.tooltip.hidden = false;
  positionTooltip(renderedPosition);
}

function positionTooltip(position) {
  if (!position) {
    return;
  }
  elements.tooltip.style.left = `${position.x + 18}px`;
  elements.tooltip.style.top = `${position.y + 18}px`;
}

function resetGraph() {
  if (!graph) {
    return;
  }
  clearSelection();
  restoreGeneratedLayout(graph, graphData.nodes);
}

function showError(error) {
  elements.loading.hidden = true;
  elements.error.hidden = false;
  elements.errorMessage.textContent = error instanceof Error ? error.message : String(error);
}

function updateGraphTheme(theme) {
  if (!graph) {
    return;
  }
  const edgeColor = theme === "dark" ? "#91a4bf" : "#64748b";
  graph.nodes().forEach((node) => {
    node.data("color", communityColor(node.data("community"), theme));
    node.data("label_color", theme === "dark" ? "#e8eef8" : "#172033");
    node.data("label_outline", theme === "dark" ? "#07111f" : "#f6f8fc");
    node.data("focal_border", theme === "dark" ? "#60a5fa" : "#2563eb");
    node.data("selection_border", theme === "dark" ? "#ffffff" : "#0f172a");
  });
  graph.edges().forEach((edge) => edge.data("color", edgeColor));
  graph.style().update();
}

function applyDocumentTheme(theme) {
  activeTheme = theme;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content =
    theme === "dark" ? "#07111f" : "#f6f8fc";
  elements.themeButton.setAttribute(
    "aria-label",
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
  );
  updateGraphTheme(theme);
}

elements.themeButton.addEventListener("click", () => {
  manualTheme = activeTheme === "dark" ? "light" : "dark";
  try {
    window.localStorage.setItem("coauthors-theme", manualTheme);
  } catch (error) {
    if (!(error instanceof DOMException)) {
      throw error;
    }
  }
  applyDocumentTheme(manualTheme);
});

mediaTheme.addEventListener("change", (event) => {
  if (!manualTheme) {
    applyDocumentTheme(resolveTheme(undefined, event.matches));
  }
});

function readStoredTheme() {
  try {
    return window.localStorage.getItem("coauthors-theme");
  } catch (error) {
    if (error instanceof DOMException) {
      return undefined;
    }
    throw error;
  }
}
