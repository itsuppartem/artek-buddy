import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../../api";
import {
  defaultMemoryScope,
  MEMORY_CHANGED_EVENT,
  memoryChapter,
  memoryDeleteName,
  memoryShelf,
  memoryTitle,
} from "../../lib/memory";
import { useSaveAck } from "../../lib/save-ack";
import type { MemoryDocument } from "../../types";
import { Button } from "../../ui/button";

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
  const [scope, setScope] = useState<"bot" | "user">(defaultMemoryScope);
  const [content, setContent] = useState("");
  const [draft, setDraft] = useState("");
  const createAck = useSaveAck();
  const editAck = useSaveAck();
  const factsRef = useRef<HTMLTextAreaElement>(null);
  const createdCardRef = useRef<HTMLDivElement>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

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
    window.addEventListener(MEMORY_CHANGED_EVENT, onChanged);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.removeEventListener(MEMORY_CHANGED_EVENT, onChanged);
    };
  }, [botId, onLater]);

  useLayoutEffect(() => {
    if (!createdId) return;
    createdCardRef.current?.scrollIntoView({ block: "nearest" });
  }, [createdId, documents]);

  async function create() {
    const text = (factsRef.current?.value ?? content).trim();
    if (!text) return;
    await createAck.run(
      async () => {
        const created = await api.memory.create({
          scope,
          botId: scope === "bot" ? botId : undefined,
          path: `entries/owner/note-${Date.now()}.md`,
          content: text,
        });
        setCreatedId(created.id);
        await refresh();
      },
      () => {
        setContent("");
        setCreating(false);
        setScope(defaultMemoryScope());
      },
    );
  }

  async function save(document: MemoryDocument) {
    await editAck.run(
      async () => {
        await api.memory.update(document.id, draft);
        await refresh();
      },
      () => setEditingId(null),
    );
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
          <span className="text-[14px] text-mute">Memory</span>
          <div className="mt-0.5 text-[12px] text-mute">
            Owner, work, and this bot — written from chat
          </div>
        </div>
        <button
          type="button"
          onClick={() => void exportMarkdown()}
          className="text-[12.5px] text-mute"
        >
          Export
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {documents.map((document) => (
          <div
            key={document.id}
            ref={document.id === createdId ? createdCardRef : undefined}
            data-testid="memory-doc"
            data-chapter={memoryChapter(document.path) ?? undefined}
            className="rounded-xl border border-hairline bg-ink px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="line-clamp-2 text-[14.5px] text-paper">{memoryTitle(document)}</div>
                <div className="mt-0.5 text-[12px] text-mute">
                  {memoryShelf(document.path)}
                  {` · ${document.scope === "user" ? "shared" : "this bot"}`}
                  {memoryChapter(document.path) ? ` · ${memoryChapter(document.path)}` : ""}
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
                  className="w-full resize-none rounded-lg border border-hairline bg-raised px-2.5 py-2 text-[13px] text-paper outline-none"
                />
                <div className="mt-2 flex gap-3 text-[12.5px] text-mute">
                  <button
                    type="button"
                    data-testid="memory-edit-save"
                    aria-live="polite"
                    disabled={editAck.state !== "idle"}
                    onClick={() => void save(document)}
                  >
                    {editAck.label}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      editAck.cancel();
                      setEditingId(null);
                    }}
                  >
                    Cancel
                  </button>
                </div>
                {editAck.error ? (
                  <p data-testid="memory-save-error" className="mt-2 text-[13px] text-danger">
                    {editAck.error}
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="mt-2">
                {document.content.includes("\n") ? (
                  <div className="line-clamp-3 whitespace-pre-wrap text-[12.5px] text-mute">
                    {document.content}
                  </div>
                ) : null}
                <div className="mt-2 flex gap-3 text-[12.5px] text-mute">
                  <button
                    type="button"
                    onClick={() => {
                      createAck.cancel();
                      setEditingId(document.id);
                      setDraft(document.content);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    data-testid="memory-remove"
                    aria-label={memoryDeleteName()}
                    onClick={() => void remove(document)}
                  >
                    {memoryDeleteName()}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      {creating ? (
        <div className="mt-3 rounded-xl border border-hairline bg-ink p-3">
          <div
            className="mb-2 inline-flex rounded-[10px] border border-hairline p-0.5"
            role="group"
            aria-label="Memory scope"
          >
            <button
              type="button"
              data-testid="memory-scope-bot"
              aria-pressed={scope === "bot"}
              onClick={() => setScope("bot")}
              className={`rounded-[8px] px-2.5 py-1 text-[12.5px] ${
                scope === "bot" ? "bg-tan font-medium text-ink" : "text-mute"
              }`}
            >
              This bot
            </button>
            <button
              type="button"
              data-testid="memory-scope-shared"
              aria-pressed={scope === "user"}
              onClick={() => setScope("user")}
              className={`rounded-[8px] px-2.5 py-1 text-[12.5px] ${
                scope === "user" ? "bg-tan font-medium text-ink" : "text-mute"
              }`}
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
            className="mt-2 w-full resize-none rounded-lg border border-hairline bg-raised px-2.5 py-2 text-[13px] text-paper outline-none"
          />
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="cream"
              size="sm"
              data-testid="memory-save"
              aria-live="polite"
              disabled={createAck.state !== "idle"}
              onClick={() => void create()}
            >
              {createAck.label}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                createAck.cancel();
                setCreating(false);
              }}
            >
              Cancel
            </Button>
          </div>
          {createAck.error ? (
            <p data-testid="memory-save-error" className="mt-2 text-[13px] text-danger">
              {createAck.error}
            </p>
          ) : null}
        </div>
      ) : (
        <button
          type="button"
          data-testid="new-memory"
          onClick={() => {
            createAck.cancel();
            editAck.cancel();
            setEditingId(null);
            setScope(defaultMemoryScope());
            setCreating(true);
          }}
          className="mt-1 flex items-center gap-2.5 px-2.5 py-2.5 text-[14.5px] text-mute"
        >
          + New memory
        </button>
      )}
    </div>
  );
}
