import { useEffect, useState } from "react";
import { api } from "../../api";
import { stripMarkdown } from "../../lib/markdown";
import { useSaveAck } from "../../lib/save-ack";
import { computerModeHint } from "../../lib/screen";
import type { Bot, ComputerMode, ComputerStatus } from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";
import { Button } from "../../ui/button";
import { ComputerModePicker } from "./ComputerModePicker";

export function computerPowerLabel(state: ComputerStatus["state"] | undefined): string {
  if (state === "running") return "Running";
  if (state === "booting") return "Booting";
  if (state === "error") return "Error";
  if (state === "suspended") return "Sleeping";
  return "Offline";
}

export function BotSettings({
  bot,
  computer,
  onClose,
  onUpdated,
  onDelete,
  onRestart,
  onStop,
  onReset,
  onLater,
}: {
  bot: Bot;
  computer: ComputerStatus | null;
  onClose: () => void;
  onUpdated: () => void;
  onDelete: (deleteMemories: boolean) => void;
  onRestart: () => Promise<void>;
  onStop: () => Promise<void>;
  onReset: () => Promise<void>;
  onLater: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(bot.name);
  const [title, setTitle] = useState(bot.title);
  const [description, setDescription] = useState(bot.description);
  const [instructions, setInstructions] = useState(bot.instructions);
  const [computerMode, setComputerMode] = useState<ComputerMode>(bot.computerMode);
  const [notifyOnFinish, setNotifyOnFinish] = useState(bot.notifyOnFinish);
  const saveAck = useSaveAck();
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [powerBusy, setPowerBusy] = useState(false);
  const [deleteMemories, setDeleteMemories] = useState(false);

  useEffect(() => {
    setName(bot.name);
    setTitle(bot.title);
    setDescription(bot.description);
    setInstructions(bot.instructions);
    setComputerMode(bot.computerMode);
    setNotifyOnFinish(bot.notifyOnFinish);
  }, [bot]);

  async function save() {
    if (!name.trim()) return;
    await saveAck.run(
      async () => {
        await api.bots.update(bot.id, {
          name: name.trim(),
          title: title.trim(),
          description: description.trim(),
          instructions: instructions.trim(),
          computerMode,
        });
        onUpdated();
      },
      () => setEditing(false),
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13.5px] text-mute">Bot Settings</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close settings"
          className="text-mute hover:text-paper"
        >
          ✕
        </button>
      </div>
      <div className="flex justify-center">
        <BotAvatar color={bot.color} size={64} />
      </div>

      {editing ? (
        <div className="mt-4 flex flex-col gap-3">
          <label className="text-[12px] text-mute">
            Name
            <input
              data-testid="bot-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
            />
          </label>
          <label className="text-[12px] text-mute">
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Code Reviewer"
              className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
            />
          </label>
          <label className="text-[12px] text-mute">
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this bot is for"
              rows={2}
              className="mt-1 w-full resize-none rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper outline-none"
            />
          </label>
          <label className="text-[12px] text-mute">
            Instructions
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Standing orders for this bot"
              rows={4}
              className="mt-1 w-full resize-none rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper outline-none"
            />
          </label>
          <ComputerModePicker value={computerMode} onChange={setComputerMode} />
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              size="sm"
              data-testid="settings-save"
              aria-live="polite"
              disabled={saveAck.state !== "idle" || !name.trim()}
              onClick={() => void save()}
            >
              {saveAck.label}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                saveAck.cancel();
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
          {saveAck.error ? (
            <p data-testid="settings-save-error" className="text-[13px] text-danger">
              {saveAck.error}
            </p>
          ) : null}
        </div>
      ) : (
        <>
          <div className="mt-6 text-[20px] font-medium text-paper">{bot.name}</div>
          <div className="mt-2 text-[14px] leading-6 text-mute">
            {stripMarkdown(bot.title || bot.description || "No description")}
          </div>
          <div className="mt-4 text-[14px] text-mute">
            Computer: {bot.computerMode === "dedicated" ? "Private" : "Team"}
          </div>
          <p className="mt-1 text-[12.5px] leading-5 text-mute">
            {computerModeHint(bot.computerMode)}
          </p>
          <div className="mt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                saveAck.cancel();
                setEditing(true);
              }}
            >
              Edit profile
            </Button>
          </div>
        </>
      )}

      <div className="mt-6 rounded-xl border border-hairline bg-ink p-3.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13.5px] text-paper">Computer</span>
          <span data-testid="computer-power-state" className="text-[12px] text-mute">
            {computerPowerLabel(computer?.state)}
          </span>
        </div>
        <p className="mt-2 text-[12.5px] leading-5 text-mute">
          Rebooting the Pi, Stop, or Restart keeps Chromium logins and downloads on disk. Reset
          destroys the box and deletes that home.
        </p>
        {bot.computerMode === "team" ? (
          <p className="mt-1.5 text-[12.5px] leading-5 text-tan">
            Reset wipes the shared Team desktop for every Team bot.
          </p>
        ) : null}
        {computer?.busyBotName ? (
          <p className="mt-1.5 text-[12.5px] leading-5 text-tan">
            {computer.busyBotName} is using this computer.
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="computer-restart"
            disabled={powerBusy || Boolean(computer?.busyBotName)}
            onClick={() => {
              setPowerBusy(true);
              void onRestart().finally(() => setPowerBusy(false));
            }}
          >
            Restart
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="computer-stop"
            disabled={powerBusy || Boolean(computer?.busyBotName)}
            onClick={() => {
              setPowerBusy(true);
              void onStop().finally(() => setPowerBusy(false));
            }}
          >
            Stop
          </Button>
          {resetting ? null : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="computer-reset"
              disabled={powerBusy || Boolean(computer?.busyBotName)}
              onClick={() => setResetting(true)}
              className="border-danger text-danger hover:bg-danger/10"
            >
              Reset…
            </Button>
          )}
        </div>
        {resetting ? (
          <div className="mt-3 rounded-lg border border-danger-bg bg-danger-bg p-3">
            <div className="text-[13px] leading-5 text-danger">
              Erase this computer’s home? Browser logins and downloads will be gone.
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                data-testid="computer-reset-confirm"
                disabled={powerBusy}
                onClick={() => {
                  setPowerBusy(true);
                  void onReset()
                    .then(() => setResetting(false))
                    .finally(() => setPowerBusy(false));
                }}
                className="border-danger text-danger hover:bg-danger/10"
              >
                Reset computer
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setResetting(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <label className="mt-5 flex items-start gap-2.5 text-[13.5px] leading-5 text-paper">
        <input
          type="checkbox"
          data-testid="notify-on-finish"
          className="mt-0.5 rounded"
          checked={notifyOnFinish}
          onChange={(event) => {
            const value = event.target.checked;
            setNotifyOnFinish(value);
            void api.bots
              .update(bot.id, { notifyOnFinish: value })
              .then(() => onUpdated())
              .catch(() => {
                setNotifyOnFinish(!value);
                onLater("Could not update notification setting");
              });
          }}
        />
        <span>Notify when this bot finishes</span>
      </label>

      {confirming ? (
        <div className="mt-8 rounded-xl border border-danger-bg bg-danger-bg p-3.5">
          <div className="text-[13.5px] leading-5 text-danger">
            Delete this chat and its history?
          </div>
          <label className="mt-2.5 flex items-center gap-2 text-[12.5px] text-paper">
            <input
              type="checkbox"
              checked={deleteMemories}
              onChange={(e) => setDeleteMemories(e.target.checked)}
              className="rounded"
            />
            Also purge bot-specific memories
          </label>
          <div className="mt-3.5 flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onDelete(deleteMemories)}
              className="border-danger text-danger hover:bg-danger/10"
            >
              Delete
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="mt-8 text-[13.5px] text-danger hover:underline"
        >
          Delete chat…
        </button>
      )}
    </div>
  );
}
