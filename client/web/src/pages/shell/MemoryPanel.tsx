import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { MemoryDocument } from "../../types";
import { Button } from "../../ui/button";

export function memoryShelf(path: string): string {
  return path.match(/^entries\/(owner|work|charter)\//)?.[1] ?? "owner";
}

export function memoryKind(path: string): string | null {
  return path.match(/^entries\/(?:(?:owner|work|charter)\/)?([a-z]+)-/)?.[1] ?? null;
}

export function memoryTitle(document: MemoryDocument): string {
  const line = document.content.trim().split("\n")[0];
  return line || memoryKind(document.path) || document.path;
}

export function MemoryPanel({
  botId,
  onLater,
}: {
  botId: string;
  onLater: (text: string) => void;
}) {
  const [documents, setDocuments] = useState<MemoryDocument[]>([]);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [scope, setScope] = useState<"bot" | "user">("user");
  const [content, setContent] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const factsRef = useRef<HTMLTextAreaElement>(null);

  async function refresh() {
    setDocuments(await api.memory.list(botId));
  }

  useEffect(() => {
    let cancelled = false;
    async function reload() {
      try {
        const docs = await api.memory.list(botId);
        if (!cancelled) setDocuments(docs);
      } catch (err) {
        if (!cancelled) {
          onLater(err instanceof Error ? err.message : "Could not load memory");
        }
      }
    }
    void reload();
    const poll = window.setInterval(() => void reload(), 10000);
    const onChanged = () => void reload();
    window.addEventListener("artek-memory-changed", onChanged);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.removeEventListener("artek-memory-changed", onChanged);
    };
  }, [botId, onLater]);

  async function create() {
    const text = (factsRef.current?.value ?? content).trim();
    if (!text) return;
    setBusy(true);
    try {
      await api.memory.create({
        scope,
        botId: scope === "bot" ? botId : undefined,
        path: `entries/owner/note-${Date.now()}.md`,
        content: text,
      });
      setContent("");
      setCreating(false);
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not save memory");
    } finally {
      setBusy(false);
    }
  }

  async function save(document: MemoryDocument) {
    setBusy(true);
    try {
      await api.memory.update(document.id, draft);
      setEditingId(null);
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not update memory");
    } finally {
      setBusy(false);
    }
  }

  async function remove(document: MemoryDocument) {
    try {
      await api.memory.remove(document.id);
      if (editingId === document.id) setEditingId(null);
      await refresh();
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not delete memory");
    }
  }

  async function exportMarkdown() {
    try {
      const markdown = await api.memory.exportMarkdown(botId);
      const blob = new Blob([markdown || ""], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "memory.md";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      onLater(err instanceof Error ? err.message : "Could not export memory");
    }
  }

  return (
    <div>
      <div className="mt-[30px] mb-3 flex items-center justify-between">
        <div>
          <span className="text-[14px] text-[#85858A]">Memory</span>
          <div className="mt-0.5 text-[12px] text-[#6C6C70]">
            Owner, work, and this bot — written from chat
          </div>
        </div>
        <button
          type="button"
          onClick={() => void exportMarkdown()}
          className="text-[12.5px] text-[#85858A]"
        >
          Export
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {documents.map((document) => (
          <div
            key={document.id}
            data-testid="memory-doc"
            className="rounded-xl border border-[#202023] bg-[#0D0D0E] px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="line-clamp-2 text-[14.5px] text-[#ECECEE]">
                  {memoryTitle(document)}
                </div>
                <div className="mt-0.5 text-[12px] text-[#6C6C70]">
                  {memoryShelf(document.path)}
                  {` · ${document.scope === "user" ? "shared" : "this bot"}`}
                  {memoryKind(document.path) ? ` · ${memoryKind(document.path)}` : ""}
                  {document.updatedAt ? ` · ${document.updatedAt.slice(0, 10)}` : ""}
                </div>
              </div>
            </div>
            {editingId === document.id ? (
              <div className="mt-2">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={4}
                  className="w-full resize-none rounded-lg border border-[#202023] bg-[#141416] px-2.5 py-2 text-[13px] text-[#ECECEE] outline-none"
                />
                <div className="mt-2 flex gap-3 text-[12.5px] text-[#85858A]">
                  <button type="button" disabled={busy} onClick={() => void save(document)}>
                    Save
                  </button>
                  <button type="button" onClick={() => setEditingId(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-2">
                {document.content.includes("\n") ? (
                  <div className="line-clamp-3 whitespace-pre-wrap text-[12.5px] text-[#9A9AA0]">
                    {document.content}
                  </div>
                ) : null}
                <div className="mt-2 flex gap-3 text-[12.5px] text-[#85858A]">
                  <button
                    type="button"
                    onClick={() => {
                      setEditingId(document.id);
                      setDraft(document.content);
                    }}
                  >
                    Edit
                  </button>
                  <button type="button" onClick={() => void remove(document)}>
                    Outdated
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      {creating ? (
        <div className="mt-3 rounded-xl border border-[#202023] bg-[#0D0D0E] p-3">
          <div className="mb-2 flex gap-2 text-[12.5px] text-[#85858A]">
            <button
              type="button"
              onClick={() => setScope("bot")}
              className={scope === "bot" ? "text-[#ECECEE]" : ""}
            >
              This bot
            </button>
            <button
              type="button"
              onClick={() => setScope("user")}
              className={scope === "user" ? "text-[#ECECEE]" : ""}
            >
              Shared
            </button>
          </div>
          <textarea
            ref={factsRef}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Facts to remember"
            rows={3}
            className="mt-2 w-full resize-none rounded-lg border border-[#202023] bg-[#141416] px-2.5 py-2 text-[13px] text-[#ECECEE] outline-none"
          />
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="cream"
              size="sm"
              data-testid="memory-save"
              disabled={busy}
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
          data-testid="new-memory"
          onClick={() => setCreating(true)}
          className="mt-1 flex items-center gap-2.5 px-2.5 py-2.5 text-[14.5px] text-[#7A7A80]"
        >
          + New memory
        </button>
      )}
    </div>
  );
}
