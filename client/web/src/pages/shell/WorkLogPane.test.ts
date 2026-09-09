import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  clipProgressLine,
  formatEstimatedUsd,
  formatRunUsage,
  groupWorkLogRuns,
  latestWorkLine,
  summarizeWorkItem,
  WorkLogPane,
  workersForRun,
} from "./WorkLogPane";

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

  it("does not mix workers from previous runs into the current group", () => {
    const workers = workersForRun(
      [
        { id: "current", parentRunId: "run-current", status: "running", task: "Current work" },
        { id: "old", parentRunId: "run-old", status: "completed", task: "Old work" },
      ],
      "run-current",
    );

    expect(workers.map((worker) => worker.id)).toEqual(["current"]);
  });

  it("keeps earlier run groups after a later lead run with no workers", () => {
    const groups = groupWorkLogRuns(
      [
        { id: "latest", parentRunId: "run-worker", status: "completed", task: "Published package" },
        { id: "old", parentRunId: "run-old", status: "completed", task: "Old work" },
      ],
      "run-status-check",
    );

    expect(groups.map((group) => group.runId)).toEqual([
      "run-status-check",
      "run-worker",
      "run-old",
    ]);
    expect(groups[1]?.workers.map((worker) => worker.id)).toEqual(["latest"]);
    expect(groups[2]?.workers.map((worker) => worker.task)).toEqual(["Old work"]);
  });

  it("lists both worker runs after the second completes", () => {
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-two",
        runStatus: "completed",
        progress: "",
        workers: [
          {
            id: "worker-2",
            parentRunId: "run-two",
            status: "completed",
            task: "please e2e-worker-progress-run",
            progress: "Checking source 2",
          },
          {
            id: "worker-1",
            parentRunId: "run-one",
            status: "completed",
            task: "please e2e-worker-block",
            progress: "Checking proposal B",
          },
        ],
        usageByRun: {
          "run-two": {
            runId: "run-two",
            inputTokens: 12,
            outputTokens: 7,
            cacheReadTokens: 1,
            cacheWriteTokens: 0,
            totalTokens: 22,
          },
          "worker-2": {
            runId: "worker-2",
            inputTokens: 3,
            outputTokens: 4,
            cacheReadTokens: 0,
            cacheWriteTokens: 0,
            totalTokens: 7,
          },
        },
        onClose: vi.fn(),
      }),
    );

    expect(html).toContain("please e2e-worker-progress-run");
    expect(html).toContain("please e2e-worker-block");
    expect(html).toContain("12 in · 7 out · 1 cache · 22 total");
    expect(html).toContain("3 in · 4 out · 7 total");
    expect(html).toContain("Checking source 2");
    expect(html.split('data-testid="work-log-run"').length - 1).toBe(2);
  });

  it("shows an estimated dollar next to token counts when the host sent one", () => {
    expect(formatEstimatedUsd(0.577576)).toBe("$0.58");
    expect(formatEstimatedUsd(null)).toBeNull();
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-cost",
        runStatus: "completed",
        workers: [],
        usageByRun: {
          "run-cost": {
            runId: "run-cost",
            inputTokens: 128700,
            outputTokens: 1242,
            cacheReadTokens: 47872,
            cacheWriteTokens: 0,
            totalTokens: 177814,
            estimatedCostUsd: 0.577576,
          },
        },
        onClose: vi.fn(),
      }),
    );
    expect(html).toContain("128700 in · 1242 out · 47872 cache · 177814 total · $0.58");
  });

  it("keeps Latest work after in-flight progress is gone", () => {
    const groups = groupWorkLogRuns(
      [{ id: "w1", parentRunId: "run-1", status: "completed", task: "Done", progress: "Packed" }],
      "run-1",
    );
    expect(latestWorkLine("", groups)).toBe("Packed");
    expect(latestWorkLine(undefined, [])).toBe("");
  });

  it("omits missing usage instead of failing the pane", () => {
    expect(formatRunUsage(null)).toBeNull();
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-current",
        runStatus: "completed",
        workers: [],
        onClose: vi.fn(),
      }),
    );
    expect(html).not.toContain("work-log-usage");
    expect(html).toContain("This run completed.");
  });

  it("does not call a cancelled run finished", () => {
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-stop",
        runStatus: "cancelled",
        workers: [],
        onClose: vi.fn(),
      }),
    );
    expect(html).toContain("Stopped by you.");
    expect(html).not.toContain("This run finished.");
    expect(html).not.toContain("Task is complete");
  });

  it("clamps a long progress dump to a short line", () => {
    const dumped = "x".repeat(400);
    expect(clipProgressLine(dumped)).toHaveLength(200);
    const html = renderToStaticMarkup(
      createElement(WorkLogPane, {
        botName: "Research desk",
        runId: "run-current",
        runStatus: "running",
        progress: dumped,
        workers: [
          {
            id: "worker-1",
            parentRunId: "run-current",
            status: "running",
            task: "Verify dates",
            progress: dumped,
          },
        ],
        onClose: vi.fn(),
      }),
    );
    expect(html).not.toContain("x".repeat(201));
  });
});
