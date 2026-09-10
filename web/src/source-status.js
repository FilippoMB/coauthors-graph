const SOURCE_NAMES = { dblp: "DBLP", semantic_scholar: "Semantic Scholar", arxiv: "arXiv" };

function formatDate(value) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)) : "not yet available";
}

export function sourceStatusView(meta) {
  const sources = Object.entries(meta.sources ?? {});
  const degraded = sources.some(([, value]) => value.status !== "fresh");
  return {
    degraded,
    summary: degraded ? "Sources · using saved data" : "Sources · up to date",
    checked: `Last checked ${formatDate(meta.last_checked_at)}`,
    rows: sources.map(([key, value]) => {
      const states = {
        fresh: "Fresh data",
        partial: "Partial update · previous records preserved",
        cached: "Unavailable · using saved data",
        unavailable: "Unavailable · no source snapshot yet",
      };
      return {
        name: SOURCE_NAMES[key] ?? key,
        status: states[value.status],
        detail: `Last complete fetch: ${formatDate(value.last_success_at)}`,
        counts: `${value.accepted_count} accepted · ${value.retained_count} retained · ${value.rejected_count} rejected`,
      };
    }),
  };
}

export function renderSourceStatus(container, meta) {
  if (!meta.sources) {
    container.hidden = true;
    return;
  }
  const view = sourceStatusView(meta);
  container.hidden = false;
  container.dataset.degraded = String(view.degraded);
  container.querySelector("summary").textContent = view.summary;
  const body = container.querySelector(".source-status-body");
  body.replaceChildren();
  const checked = document.createElement("p");
  checked.textContent = `${view.checked}. Graph generated ${formatDate(meta.generated_at)}. Refreshes weekly on Mondays.`;
  body.append(checked);
  for (const row of view.rows) {
    const section = document.createElement("section");
    const heading = document.createElement("strong");
    heading.textContent = row.name;
    section.append(heading);
    for (const text of [row.status, row.detail, row.counts]) {
      const line = document.createElement("span");
      line.textContent = text;
      section.append(line);
    }
    body.append(section);
  }
}
