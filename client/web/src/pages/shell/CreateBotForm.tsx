import { useState } from "react";
import type { ComputerMode } from "../../types";
import { ComputerModePicker } from "./ComputerModePicker";

export function CreateBotForm({
  onCreate,
  onCancel,
}: {
  onCreate: (input: {
    name: string;
    title: string;
    description: string;
    computerMode: ComputerMode;
  }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [computerMode, setComputerMode] = useState<ComputerMode>("team");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        onCreate({ name, title, description, computerMode });
      }}
    >
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13.5px] text-mute">New bot</span>
        <button
          type="button"
          aria-label="Cancel create"
          data-testid="create-cancel"
          onClick={onCancel}
        >
          ✕
        </button>
      </div>
      <label className="mt-6 block text-[14px] text-mute">
        Name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name this bot"
          className="mt-2 w-full rounded-[10px] border border-hairline bg-raised px-3.5 py-3 text-paper"
        />
      </label>
      <label className="mt-4 block text-[14px] text-mute">
        Title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Describe what this bot does"
          className="mt-2 w-full rounded-[10px] border border-hairline bg-raised px-3.5 py-3 text-paper"
        />
      </label>
      <label className="mt-4 block text-[14px] text-mute">
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="What this bot is for"
          rows={4}
          className="mt-2 w-full rounded-[10px] border border-hairline bg-raised px-3.5 py-3 text-paper"
        />
      </label>
      <ComputerModePicker value={computerMode} onChange={setComputerMode} />
      <button
        type="submit"
        disabled={!name.trim()}
        className="mt-5 rounded-[10px] bg-tan px-4 py-2 text-ink disabled:opacity-40"
      >
        Create
      </button>
    </form>
  );
}
