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
        <span className="text-[13.5px] text-[#85858A]">New bot</span>
        <button
          type="button"
          aria-label="Cancel create"
          data-testid="create-cancel"
          onClick={onCancel}
        >
          ✕
        </button>
      </div>
      <label className="mt-6 block text-[14px] text-[#85858A]">
        Name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name this bot"
          className="mt-2 w-full rounded-[11px] border border-[#26262A] bg-transparent px-3.5 py-3 text-[#ECECEE]"
        />
      </label>
      <label className="mt-4 block text-[14px] text-[#85858A]">
        Title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Describe what this bot does"
          className="mt-2 w-full rounded-[11px] border border-[#26262A] bg-transparent px-3.5 py-3 text-[#ECECEE]"
        />
      </label>
      <label className="mt-4 block text-[14px] text-[#85858A]">
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="What this bot is for"
          rows={4}
          className="mt-2 w-full rounded-[11px] border border-[#26262A] bg-transparent px-3.5 py-3 text-[#ECECEE]"
        />
      </label>
      <ComputerModePicker value={computerMode} onChange={setComputerMode} />
      <button
        type="submit"
        disabled={!name.trim()}
        className="mt-5 rounded-[11px] bg-[#F1F1EF] px-4 py-2 text-[#17171A] disabled:opacity-40"
      >
        Create
      </button>
    </form>
  );
}
