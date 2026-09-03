import type { Subagent } from "../types";

const ACTIVE = new Set(["queued", "running"]);

export function inFlightProgressText(subagents: Subagent[] | undefined): string {
  const ranked = (subagents ?? [])
    .filter((row) => ACTIVE.has(row.status) && (row.progress ?? "").trim())
    .slice()
    .sort(compareActivity);
  const top = ranked[0];
  if (!top) return "";
  const step = (top.progress ?? "").trim();
  const leftover = (top.progressRemaining ?? "").trim();
  if (leftover) return `Still working: ${step}. Next: ${leftover}.`;
  return `Still working: ${step}.`;
}

function compareActivity(left: Subagent, right: Subagent): number {
  const seq = (right.activitySeq ?? 0) - (left.activitySeq ?? 0);
  if (seq) return seq;
  const byTime = (right.lastActivityAt ?? "").localeCompare(left.lastActivityAt ?? "");
  if (byTime) return byTime;
  return left.id.localeCompare(right.id);
}
