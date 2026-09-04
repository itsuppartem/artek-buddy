import { type FormEvent, useMemo, useState } from "react";
import { type BotTaskStage, botTaskStage, suggestTaskBot } from "../../lib/task-flow";
import type { Bot } from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";

const sections: Array<{ stage: BotTaskStage; title: string; empty: string }> = [
  { stage: "decision", title: "Needs your decision", empty: "Nothing is waiting on you." },
  { stage: "working", title: "In progress", empty: "No tasks are running." },
  { stage: "ready", title: "Ready for you", empty: "No unread results." },
];

export function TodayView({
  bots,
  botsReady,
  onOpenBot,
  onStartTask,
  onOpenRoutines,
  onCreateBot,
}: {
  bots: Bot[];
  botsReady: boolean;
  onOpenBot: (id: string) => void;
  onStartTask: (botId: string, task: string) => void | Promise<void>;
  onOpenRoutines: () => void;
  onCreateBot: () => void;
}) {
  const [task, setTask] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const suggested = useMemo(() => suggestTaskBot(bots, task), [bots, task]);
  const grouped = useMemo(
    () =>
      new Map(
        sections.map(({ stage }) => [stage, bots.filter((bot) => botTaskStage(bot) === stage)]),
      ),
    [bots],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = task.trim();
    if (!botsReady || starting) return;
    if (!suggested) {
      onCreateBot();
      return;
    }
    if (!text) return;
    setStarting(true);
    setError("");
    try {
      await onStartTask(suggested.id, text);
      setTask("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start that task");
    } finally {
      setStarting(false);
    }
  }

  return (
    <main data-testid="today-view" className="ab-scroll min-w-0 flex-1 overflow-y-auto bg-ink">
      <div className="mx-auto w-full max-w-[1180px] px-6 py-7 lg:px-8">
        <header className="mb-5">
          <p className="font-mono text-[10px] tracking-[0.08em] text-tan uppercase">
            Your workspace
          </p>
          <h1 className="mt-2 text-[28px] font-bold tracking-[-0.04em] text-paper">Today</h1>
          <p className="mt-1 text-[13px] text-mute">
            Start with an outcome. Return only for decisions and results.
          </p>
        </header>

        <form
          data-testid="task-first-start"
          onSubmit={submit}
          className="rounded-[15px] border border-hairline bg-plate p-4"
        >
          <label htmlFor="task-outcome" className="text-[14px] font-bold text-paper">
            What needs doing?
          </label>
          <p className="mt-1 text-[12px] text-mute">
            Artek suggests the most relevant bot before anything starts.
          </p>
          <div className="mt-3 flex min-h-12 items-end gap-2 rounded-[12px] border border-hairline bg-ink p-1.5 pl-3">
            <textarea
              id="task-outcome"
              aria-label="Describe the outcome"
              value={task}
              rows={1}
              placeholder="Ask, compare, prepare, check, or make something…"
              onChange={(event) => setTask(event.target.value)}
              className="max-h-32 min-h-9 min-w-0 flex-1 resize-none bg-transparent py-2 text-[14px] leading-5 text-paper"
            />
            <button
              type="submit"
              disabled={!botsReady || starting || Boolean(suggested && !task.trim())}
              className="min-h-10 shrink-0 rounded-[10px] bg-tan px-4 text-[13px] font-bold text-ink transition disabled:opacity-40"
            >
              {!botsReady
                ? "Loading bots…"
                : starting
                  ? "Starting…"
                  : suggested
                    ? `Continue with ${suggested.name}`
                    : "Create your first bot"}
            </button>
          </div>
          {task.trim() && suggested ? (
            <p data-testid="task-router" className="mt-2 text-[11.5px] text-mute">
              Suggested: <span className="font-semibold text-paper">{suggested.name}</span> · you
              can change the bot in chat before sending another task.
            </p>
          ) : null}
          {error ? (
            <p data-testid="task-start-error" className="mt-2 text-[12px] text-danger">
              {error}
            </p>
          ) : null}
        </form>

        {botsReady ? (
          <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.75fr)]">
            <div>
              {sections.slice(0, 2).map((section) => (
                <TaskSection
                  key={section.stage}
                  {...section}
                  bots={grouped.get(section.stage) ?? []}
                  onOpenBot={onOpenBot}
                />
              ))}
            </div>
            <div>
              {sections.slice(2).map((section) => (
                <TaskSection
                  key={section.stage}
                  {...section}
                  bots={grouped.get(section.stage) ?? []}
                  onOpenBot={onOpenBot}
                />
              ))}
              <section className="mt-7 border-t border-hairline pt-4">
                <h2 className="text-[14px] font-bold text-paper">
                  Make successful work repeatable
                </h2>
                <p className="mt-1.5 text-[12px] leading-5 text-mute">
                  Turn reviewed results into a schedule. Choose the instructions, timing, and
                  whether it stays on.
                </p>
                <button
                  type="button"
                  onClick={onOpenRoutines}
                  className="mt-3 min-h-10 rounded-[10px] border border-hairline bg-plate px-3 text-[12px] font-bold text-paper"
                >
                  Open routines
                </button>
              </section>
            </div>
          </div>
        ) : (
          <p className="mt-6 border-b border-hairline py-5 text-[12px] text-mute">
            Loading your workspace…
          </p>
        )}
      </div>
    </main>
  );
}

function TaskSection({
  stage,
  title,
  empty,
  bots,
  onOpenBot,
}: {
  stage: BotTaskStage;
  title: string;
  empty: string;
  bots: Bot[];
  onOpenBot: (id: string) => void;
}) {
  return (
    <section data-task-stage={stage} className="mb-7">
      <div className="flex items-center justify-between border-b border-hairline pb-2.5">
        <h2 className="text-[14px] font-bold text-paper">{title}</h2>
        <span className="font-mono text-[10px] text-mute uppercase">{bots.length}</span>
      </div>
      {bots.length ? (
        <div>
          {bots.map((bot) => (
            <button
              key={bot.id}
              type="button"
              onClick={() => onOpenBot(bot.id)}
              className="flex min-h-[68px] w-full items-center gap-3 border-b border-hairline py-3 text-left"
            >
              <BotAvatar color={bot.color} size={40} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-bold text-paper">{bot.name}</span>
                <span className="mt-1 block truncate text-[12px] text-mute">
                  {bot.preview || bot.title}
                </span>
              </span>
              <span
                className={`font-mono text-[9px] uppercase ${
                  stage === "decision"
                    ? "text-copper"
                    : stage === "working"
                      ? "text-sage"
                      : "text-tan"
                }`}
              >
                {stage === "decision" ? "Review" : stage === "working" ? "Working" : "Open result"}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="border-b border-hairline py-4 text-[12px] text-mute">{empty}</p>
      )}
    </section>
  );
}
