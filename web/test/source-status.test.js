import { describe, expect, it } from "vitest";
import { sourceStatusView } from "../src/source-status.js";

const meta = {
  last_checked_at: "2026-09-10T12:00:00Z",
  sources: {
    dblp: { status: "cached", last_success_at: "2026-08-31T12:00:00Z", accepted_count: 0, retained_count: 98, rejected_count: 0 },
    arxiv: { status: "fresh", last_success_at: "2026-09-10T12:00:00Z", accepted_count: 64, retained_count: 0, rejected_count: 0 },
  },
};

describe("source freshness presentation", () => {
  it("distinguishes checking from a complete successful fetch", () => {
    const view = sourceStatusView(meta);
    expect(view.degraded).toBe(true);
    expect(view.summary).toContain("saved data");
    expect(view.rows[0].name).toBe("DBLP");
    expect(view.rows[0].status).toContain("using saved data");
    expect(view.rows[0].detail).not.toBe(view.rows[1].detail);
    expect(view.rows[0].counts).toContain("98 retained");
  });

  it("does not invent a success date for an unavailable source", () => {
    const view = sourceStatusView({ ...meta, sources: { dblp: { ...meta.sources.dblp, status: "unavailable", last_success_at: null } } });
    expect(view.rows[0].detail).toContain("not yet available");
    expect(view.rows[0].status).toContain("no source snapshot");
  });

  it("shows healthy and partial runs distinctly", () => {
    expect(sourceStatusView({ ...meta, sources: { arxiv: meta.sources.arxiv } }).degraded).toBe(false);
    expect(sourceStatusView({ ...meta, sources: { arxiv: { ...meta.sources.arxiv, status: "partial" } } }).rows[0].status).toContain("Partial update");
  });
});
