import { workLogLatestFallback, workLogRunStatusLabel } from "../../lib/task-flow";
import { IconClose } from "../../ui/icons";

export const PROGRESS_LINE_MAX = 200;
export const WORK_LOG_GROUP_LIMIT = 40;

export type WorkLogWorker = {
  id: string;
  parentRunId?: string | null;
  status: string;
  task: string;
  progress?: string | null;
  lastToolName?: string | null;
  lastActivityAt?: string | null;
  createdAt?: string | null;
};

export type WorkLogUsage = {
  runId: string;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens: number;
  estimatedCostUsd?: number | null;
};

export type WorkLogGroup = {
  runId: string;
  workers: WorkLogWorker[];
};

export function summarizeWorkItem(task: string, maxLength = 76): string {
  const compact = task.replace(/\s+/g, " ").trim();
  const firstSentence = compact.match(/^.*?[.!?](?=\s|$)/)?.[0];
  if (firstSentence && firstSentence.length <= maxLength) return firstSentence;
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 1).trimEnd()}…`;
}

export function clipProgressLine(text: string, maxLength = PROGRESS_LINE_MAX): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return compact.slice(0, maxLength).trimEnd();
}

export function workersForRun(workers: WorkLogWorker[], runId?: string | null): WorkLogWorker[] {
  const current = runId ? workers.filter((worker) => worker.parentRunId === runId) : [];
  if (current.length) return current;
  const latestRunId = workers.find((worker) => worker.parentRunId)?.parentRunId;
  return latestRunId ? workers.filter((worker) => worker.parentRunId === latestRunId) : [];
}

export function groupWorkLogRuns(
  workers: WorkLogWorker[],
  currentRunId?: string | null,
): WorkLogGroup[] {
  const byRun = new Map<string, WorkLogWorker[]>();
  const seen: string[] = [];
  function ensure(runId: string): WorkLogWorker[] {
    let rows = byRun.get(runId);
    if (!rows) {
      rows = [];
      byRun.set(runId, rows);
      seen.push(runId);
    }
    return rows;
  }
  for (const worker of workers) {
    const runId = worker.parentRunId;
    if (!runId) continue;
    ensure(runId).push(worker);
  }
  if (currentRunId) ensure(currentRunId);
  const ordered = currentRunId ? [currentRunId, ...seen.filter((id) => id !== currentRunId)] : seen;
  return ordered.slice(0, WORK_LOG_GROUP_LIMIT).map((runId) => ({
    runId,
    workers: byRun.get(runId) ?? [],
  }));
}

export function formatEstimatedUsd(usd?: number | null): string | null {
  if (usd == null || !Number.isFinite(usd)) return null;
  return `$${usd.toFixed(2)}`;
}

export function formatRunUsage(usage?: WorkLogUsage | null): string | null {
  if (!usage) return null;
  const parts = [
    `${usage.inputTokens} in`,
    `${usage.outputTokens} out`,
    `${usage.totalTokens} total`,
  ];
  if (usage.cacheReadTokens > 0 || usage.cacheWriteTokens > 0) {
    parts.splice(2, 0, `${usage.cacheReadTokens + usage.cacheWriteTokens} cache`);
  }
  const dollars = formatEstimatedUsd(usage.estimatedCostUsd);
  if (dollars) parts.push(dollars);
  return parts.join(" · ");
}

export function usageFromRecords(
  records: Array<{
    runId?: string | null;
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
    totalTokens: number;
    estimatedCostUsd?: number | null;
  }>,
): Record<string, WorkLogUsage> {
  const out: Record<string, WorkLogUsage> = {};
  for (const row of records) {
    if (!row.runId) continue;
    out[row.runId] = {
      runId: row.runId,
      inputTokens: row.inputTokens,
      outputTokens: row.outputTokens,
      cacheReadTokens: row.cacheReadTokens ?? 0,
      cacheWriteTokens: row.cacheWriteTokens ?? 0,
      totalTokens: row.totalTokens,
      estimatedCostUsd: row.estimatedCostUsd,
    };
  }
  return out;
}

export function latestWorkLine(
  progress: string | null | undefined,
  groups: WorkLogGroup[],
): string {
  const live = clipProgressLine(progress || "");
  if (live) return live;
  for (const group of groups) {
    for (const worker of group.workers) {
      const step = clipProgressLine(worker.progress || "");
      if (step) return step;
    }
  }
  return "";
}

export function WorkLogPane({
  botName,
  runId,
  runStatus,
  progress,
  workers,
  usageByRun,
  onClose,
}: {
  botName: string;
  runId?: string | null;
  runStatus?: string;
  progress?: string | null;
  workers: WorkLogWorker[];
  usageByRun?: Record<string, WorkLogUsage>;
  onClose: () => void;
}) {
  const groups = groupWorkLogRuns(workers, runId);
  const latestLine = latestWorkLine(progress, groups);
  const latestStatus = workLogRunStatusLabel(runStatus || groups[0]?.workers[0]?.status);

  return (
    <div data-testid="work-log-pane">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] tracking-[0.07em] text-tan uppercase">
            Operational detail
          </p>
          <h2 className="mt-1.5 text-[18px] font-bold tracking-[-0.03em] text-paper">Work log</h2>
          <p className="mt-1 text-[12px] text-mute">{botName}</p>
        </div>
        <button
          type="button"
          aria-label="Close work log"
          onClick={onClose}
          className="grid h-9 w-9 place-items-center rounded-[10px] border border-hairline bg-raised text-paper"
        >
          <IconClose />
        </button>
      </header>

      <section className="mt-5 rounded-[13px] border border-hairline bg-plate p-3.5">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[13px] font-bold text-paper">Latest work</h3>
          <span className="font-mono text-[9px] text-sage uppercase">{latestStatus}</span>
        </div>
        <p className="mt-2 text-[12.5px] leading-5 text-mute">
          {latestLine || workLogLatestFallback(runStatus)}
        </p>
      </section>

      <section className="mt-6">
        <div className="flex items-center justify-between border-b border-hairline pb-2.5">
          <h3 className="text-[13px] font-bold text-paper">Runs</h3>
          <span className="font-mono text-[9px] text-mute uppercase">{groups.length}</span>
        </div>
        {groups.length ? (
          groups.map((group) => (
            <RunGroup
              key={group.runId}
              group={group}
              usage={usageByRun?.[group.runId]}
              usageByRun={usageByRun}
              current={group.runId === runId}
              runStatus={group.runId === runId ? runStatus : undefined}
            />
          ))
        ) : (
          <p className="border-b border-hairline py-4 text-[12px] text-mute">
            No runs in this chat yet.
          </p>
        )}
      </section>

      <p className="mt-6 text-[11px] leading-5 text-mute">
        This log explains progress and tool use. Results and decisions stay in the conversation.
      </p>
    </div>
  );
}

function RunGroup({
  group,
  usage,
  usageByRun,
  current,
  runStatus,
}: {
  group: WorkLogGroup;
  usage?: WorkLogUsage;
  usageByRun?: Record<string, WorkLogUsage>;
  current: boolean;
  runStatus?: string;
}) {
  const usageLine = formatRunUsage(usage);
  const status = group.workers[0]?.status || workLogRunStatusLabel(runStatus, current);
  return (
    <section
      data-testid="work-log-run"
      data-run-id={group.runId}
      className="border-b border-hairline py-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[9px] text-tan uppercase">
            {current ? "This run" : "Earlier run"}
          </p>
          {usageLine ? (
            <p data-testid="work-log-usage" className="mt-1 text-[11.5px] text-paper">
              {usageLine}
            </p>
          ) : null}
        </div>
        <span className="shrink-0 font-mono text-[9px] text-sage uppercase">{status}</span>
      </div>
      {group.workers.length ? (
        group.workers.map((worker) => (
          <WorkerRow key={worker.id} worker={worker} usage={usageByRun?.[worker.id]} />
        ))
      ) : (
        <p className="mt-2 text-[12px] text-mute">No background workers in this run.</p>
      )}
    </section>
  );
}

function WorkerRow({ worker, usage }: { worker: WorkLogWorker; usage?: WorkLogUsage }) {
  const usageLine = formatRunUsage(usage);
  return (
    <details data-testid="work-log-worker" className="group mt-1">
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 py-2.5 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1">
          <strong className="line-clamp-2 block break-words text-[12.5px] leading-[18px] text-paper">
            {summarizeWorkItem(worker.task)}
          </strong>
          {worker.progress ? (
            <span className="mt-0.5 block truncate text-[11px] text-mute">
              {clipProgressLine(worker.progress)}
            </span>
          ) : null}
          {usageLine ? (
            <span
              data-testid="work-log-usage"
              className="mt-0.5 block truncate text-[11px] text-mute"
            >
              {usageLine}
            </span>
          ) : null}
        </span>
        <span className="shrink-0 font-mono text-[9px] text-sage uppercase">{worker.status}</span>
      </summary>
      <div className="mb-3 rounded-[10px] bg-raised p-3">
        {summarizeWorkItem(worker.task) !== worker.task.trim() ? (
          <p className="max-h-40 overflow-y-auto break-words text-[11.5px] leading-5 text-mute">
            {worker.task}
          </p>
        ) : null}
        {worker.progress ? (
          <p className="mt-2 break-words text-[11.5px] leading-5 text-paper">
            {clipProgressLine(worker.progress)}
          </p>
        ) : null}
        {worker.lastToolName ? (
          <p className="mt-2 font-mono text-[9px] text-mute">Tool: {worker.lastToolName}</p>
        ) : null}
      </div>
    </details>
  );
}
