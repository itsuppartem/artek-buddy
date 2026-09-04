import { IconClose } from "../../ui/icons";

export type WorkLogWorker = {
  id: string;
  parentRunId?: string | null;
  status: string;
  task: string;
  progress?: string | null;
  lastToolName?: string | null;
};

export function summarizeWorkItem(task: string, maxLength = 76): string {
  const compact = task.replace(/\s+/g, " ").trim();
  const firstSentence = compact.match(/^.*?[.!?](?=\s|$)/)?.[0];
  if (firstSentence && firstSentence.length <= maxLength) return firstSentence;
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, maxLength - 1).trimEnd()}…`;
}

export function workersForRun(workers: WorkLogWorker[], runId?: string | null): WorkLogWorker[] {
  if (!runId) return [];
  return workers.filter((worker) => worker.parentRunId === runId);
}

export function WorkLogPane({
  botName,
  runId,
  runStatus,
  progress,
  workers,
  onClose,
}: {
  botName: string;
  runId?: string | null;
  runStatus?: string;
  progress?: string | null;
  workers: WorkLogWorker[];
  onClose: () => void;
}) {
  const currentWorkers = workersForRun(workers, runId);

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
          <h3 className="text-[13px] font-bold text-paper">Current run</h3>
          <span className="font-mono text-[9px] text-sage uppercase">
            {runStatus || "No active run"}
          </span>
        </div>
        <p className="mt-2 text-[12.5px] leading-5 text-mute">
          {progress || "Artek has not published a detailed progress step."}
        </p>
      </section>

      <section className="mt-6">
        <div className="flex items-center justify-between border-b border-hairline pb-2.5">
          <h3 className="text-[13px] font-bold text-paper">Workers</h3>
          <span className="font-mono text-[9px] text-mute uppercase">{currentWorkers.length}</span>
        </div>
        {currentWorkers.length ? (
          currentWorkers.map((worker) => (
            <details
              key={worker.id}
              data-testid="work-log-worker"
              className="group border-b border-hairline"
            >
              <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 py-2.5 [&::-webkit-details-marker]:hidden">
                <span className="min-w-0 flex-1">
                  <strong className="line-clamp-2 block break-words text-[12.5px] leading-[18px] text-paper">
                    {summarizeWorkItem(worker.task)}
                  </strong>
                  {worker.progress ? (
                    <span className="mt-0.5 block truncate text-[11px] text-mute">
                      {worker.progress}
                    </span>
                  ) : null}
                </span>
                <span className="shrink-0 font-mono text-[9px] text-sage uppercase">
                  {worker.status}
                </span>
              </summary>
              <div className="mb-3 rounded-[10px] bg-raised p-3">
                {summarizeWorkItem(worker.task) !== worker.task.trim() ? (
                  <p className="max-h-40 overflow-y-auto break-words text-[11.5px] leading-5 text-mute">
                    {worker.task}
                  </p>
                ) : null}
                {worker.progress ? (
                  <p className="mt-2 break-words text-[11.5px] leading-5 text-paper">
                    {worker.progress}
                  </p>
                ) : null}
                {worker.lastToolName ? (
                  <p className="mt-2 font-mono text-[9px] text-mute">Tool: {worker.lastToolName}</p>
                ) : null}
              </div>
            </details>
          ))
        ) : (
          <p className="border-b border-hairline py-4 text-[12px] text-mute">
            No background workers in this run.
          </p>
        )}
      </section>

      <p className="mt-6 text-[11px] leading-5 text-mute">
        This log explains progress and tool use. Results and decisions stay in the conversation.
      </p>
    </div>
  );
}
