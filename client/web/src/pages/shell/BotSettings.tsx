import { useEffect, useState } from "react";
import { api } from "../../api";
import { stripMarkdown } from "../../lib/markdown";
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
  const [saving, setSaving] = useState(false);
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
    setSaving(true);
    try {
      await api.bots.update(bot.id, {
        name: name.trim(),
        title: title.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
        computerMode,
      });
      setEditing(false);
      onUpdated();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Failed to update bot");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13.5px] text-[#85858A]">Bot Settings</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close settings"
          className="text-[#85858A] hover:text-[#ECECEE]"
        >
          ✕
        </button>
      </div>
      <div className="flex justify-center">
        <BotAvatar color={bot.color} size={64} />
      </div>

      {editing ? (
        <div className="mt-4 flex flex-col gap-3">
          <label className="text-[12px] text-[#85858A]">
            Name
            <input
              data-testid="bot-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
            />
          </label>
          <label className="text-[12px] text-[#85858A]">
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Code Reviewer"
              className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
            />
          </label>
          <label className="text-[12px] text-[#85858A]">
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 w-full resize-none rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </label>
          <label className="text-[12px] text-[#85858A]">
            Instructions (Prompt)
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={4}
              className="mt-1 w-full resize-none rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </label>
          <ComputerModePicker value={computerMode} onChange={setComputerMode} />
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={saving || !name.trim()}
              onClick={() => void save()}
            >
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-6 text-[20px] font-medium text-[#ECECEE]">{bot.name}</div>
          <div className="mt-2 text-[14px] leading-6 text-[#85858A]">
            {stripMarkdown(bot.title || bot.description || "No description")}
          </div>
          <div className="mt-4 text-[14px] text-[#A8A8AD]">
            Computer: {bot.computerMode === "dedicated" ? "Private" : "Team"}
          </div>
          <p className="mt-1 text-[12.5px] leading-5 text-[#6C6C70]">
            {computerModeHint(bot.computerMode)}
          </p>
          <div className="mt-3">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
              Edit profile
            </Button>
          </div>
        </>
      )}

      <div className="mt-6 rounded-xl border border-[#232326] bg-[#101012] p-3.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13.5px] text-[#C9C9CE]">Computer</span>
          <span data-testid="computer-power-state" className="text-[12px] text-[#85858A]">
            {computerPowerLabel(computer?.state)}
          </span>
        </div>
        <p className="mt-2 text-[12.5px] leading-5 text-[#6C6C70]">
          Rebooting the Pi, Stop, or Restart keeps Chromium logins and downloads on disk. Reset
          destroys the box and deletes that home.
        </p>
        {bot.computerMode === "team" ? (
          <p className="mt-1.5 text-[12.5px] leading-5 text-[#8A7A5C]">
            Reset wipes the shared Team desktop for every Team bot.
          </p>
        ) : null}
        {computer?.busyBotName ? (
          <p className="mt-1.5 text-[12.5px] leading-5 text-[#8A7A5C]">
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
              className="border-[#FF5364] text-[#FF5364] hover:bg-[#FF5364]/10"
            >
              Reset…
            </Button>
          )}
        </div>
        {resetting ? (
          <div className="mt-3 rounded-lg border border-[#3A2222] bg-[#1A1212] p-3">
            <div className="text-[13px] leading-5 text-[#E8A0A0]">
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
                className="border-[#FF5364] text-[#FF5364] hover:bg-[#FF5364]/10"
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

      <label className="mt-5 flex items-start gap-2.5 text-[13.5px] leading-5 text-[#C9C9CE]">
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
        <div className="mt-8 rounded-xl border border-[#3A2222] bg-[#1A1212] p-3.5">
          <div className="text-[13.5px] leading-5 text-[#E8A0A0]">
            Delete this chat and its history?
          </div>
          <label className="mt-2.5 flex items-center gap-2 text-[12.5px] text-[#C9C9CE]">
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
              className="border-[#FF5364] text-[#FF5364] hover:bg-[#FF5364]/10"
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
          className="mt-8 text-[13.5px] text-[#E38A8A] hover:underline"
        >
          Delete chat…
        </button>
      )}
    </div>
  );
}
