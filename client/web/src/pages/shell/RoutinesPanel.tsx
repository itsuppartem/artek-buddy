import { useEffect, useState } from "react";
import { api } from "../../api";
import { isCronShape } from "../../lib/cron";
import type { Routine } from "../../types";
import { Button } from "../../ui/button";

export function RoutinesPanel({
  botId,
  onLater,
}: {
  botId: string;
  onLater: (text: string) => void;
}) {
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [cron, setCron] = useState("0 9 * * *");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setRoutines(await api.routines.list(botId));
  }

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      onLater(err instanceof Error ? err.message : "Could not load routines");
    });
    const poll = window.setInterval(() => void refresh().catch(() => undefined), 10000);
    return () => window.clearInterval(poll);
  }, [botId]);

  async function create() {
    if (!name.trim() || !prompt.trim() || !isCronShape(cron)) return;
    setBusy(true);
    try {
      await api.routines.create({
        botId,
        name: name.trim(),
        prompt: prompt.trim(),
        cron: cron.trim(),
        timezone: "UTC",
        active: true,
      });
      setName("");
      setPrompt("");
      setCron("0 9 * * *");
      setCreating(false);
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not create routine");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(routine: Routine) {
    try {
      await api.routines.update(routine.id, { active: !routine.active });
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not update routine");
    }
  }

  async function runNow(routine: Routine) {
    try {
      await api.routines.testRun(routine.id);
      onLater("Routine started");
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Routine did not start");
    }
  }

  async function remove(routine: Routine) {
    try {
      await api.routines.remove(routine.id);
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not delete routine");
    }
  }

  return (
    <div>
      <div className="mt-[30px] mb-3 text-[14px] text-mute">Routines</div>
      <div className="flex flex-col gap-2">
        {routines.map((routine) => (
          <div
            key={routine.id}
            data-testid="routine-row"
            className="rounded-xl border border-hairline bg-ink px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[14.5px] text-paper">{routine.name}</div>
                <div className="mt-0.5 font-mono text-[12px] text-mute">{routine.cron}</div>
                <div className="mt-0.5 text-[12px] text-mute">
                  {routine.active
                    ? routine.nextRunAt
                      ? `next ${routine.nextRunAt.replace("T", " ").replace("Z", " UTC")}`
                      : "scheduled"
                    : "paused"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void toggle(routine)}
                className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${
                  routine.active ? "bg-sage-bg text-sage" : "bg-plate text-mute"
                }`}
              >
                {routine.active ? "on" : "off"}
              </button>
            </div>
            <div className="mt-2 flex gap-3 text-[12.5px] text-mute">
              <button type="button" onClick={() => void runNow(routine)}>
                Run
              </button>
              <button type="button" onClick={() => void remove(routine)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
      {creating ? (
        <div className="mt-3 rounded-xl border border-hairline bg-ink p-3">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            className="h-9 w-full rounded-lg border border-hairline bg-raised px-2.5 text-[13px] text-paper outline-none"
          />
          <input
            value={cron}
            onChange={(event) => setCron(event.target.value)}
            placeholder="0 9 * * *"
            className="mt-2 h-9 w-full rounded-lg border border-hairline bg-raised px-2.5 font-mono text-[13px] text-paper outline-none"
          />
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Prompt to send"
            rows={3}
            className="mt-2 w-full resize-none rounded-lg border border-hairline bg-raised px-2.5 py-2 text-[13px] text-paper outline-none"
          />
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="cream"
              size="sm"
              disabled={busy || !name.trim() || !prompt.trim() || !isCronShape(cron)}
              onClick={() => void create()}
            >
              Save
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setCreating(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          data-testid="new-routine"
          onClick={() => setCreating(true)}
          className="mt-1 flex items-center gap-2.5 px-2.5 py-2.5 text-[14.5px] text-mute"
        >
          + New routine
        </button>
      )}
    </div>
  );
}
