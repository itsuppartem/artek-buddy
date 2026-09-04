import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { summarizeWorkItem, WorkLogPane, workersForRun } from "./WorkLogPane";

describe("WorkLogPane", () => {
  it("keeps operational detail available without placing it in the conversation", () => {
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-current",
        runStatus: "running",
        progress: "Reading source 3 of 4",
        workers: [
          {
            id: "worker-1",
            parentRunId: "run-current",
            status: "running",
            task: "Verify changed delivery dates",
            progress: "Checking proposal B",
            lastToolName: "read_file",
          },
        ],
        onClose: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="work-log-pane"');
    expect(html).toContain("Work log");
    expect(html).toContain("Reading source 3 of 4");
    expect(html).toContain("Verify changed delivery dates");
    expect(html).toContain("Checking proposal B");
    expect(html).toContain("read_file");
    expect(html).toContain("Operational detail");
    expect(html).toContain("<details");
  });

  it("turns a pasted worker brief into a scannable row title", () => {
    const summary = summarizeWorkItem(
      "Resume interrupted RN-1035 work on RN-017. Previous session was patched and was about to rebuild the dev stack. Do not start a new plan.",
    );

    expect(summary).toBe("Resume interrupted RN-1035 work on RN-017.");
    expect(summary.length).toBeLessThan(80);
  });

  it("does not mix workers from previous runs into the current log", () => {
    const workers = workersForRun(
      [
        { id: "current", parentRunId: "run-current", status: "running", task: "Current work" },
        { id: "old", parentRunId: "run-old", status: "completed", task: "Old work" },
      ],
      "run-current",
    );

    expect(workers.map((worker) => worker.id)).toEqual(["current"]);
  });

  it("keeps the latest worker run when a later lead run has no workers", () => {
    const workers = workersForRun(
      [
        { id: "latest", parentRunId: "run-worker", status: "completed", task: "Published package" },
        { id: "old", parentRunId: "run-old", status: "completed", task: "Old work" },
      ],
      "run-status-check",
    );

    expect(workers.map((worker) => worker.id)).toEqual(["latest"]);
  });
});
