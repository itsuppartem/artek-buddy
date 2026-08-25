import { useEffect, useState } from "react";
import { ApiError, api } from "../../api";
import type { Connection, ConnectionCatalogItem, ConnectionKeyStatus } from "../../types";
import { Button } from "../../ui/button";
import { IconClose } from "../../ui/icons";

export function PluginsPane({
  onClose,
  onAppsChange,
}: {
  onClose: () => void;
  onAppsChange?: () => void;
}) {
  const [status, setStatus] = useState<ConnectionKeyStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [replace, setReplace] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ConnectionCatalogItem[]>([]);
  const [rows, setRows] = useState<Connection[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const configured = Boolean(status?.configured);
  const showKeyField = !configured || replace;

  useEffect(() => {
    void refresh("");
  }, []);

  async function refresh(search: string) {
    const next = await api.connections.status();
    setStatus(next);
    if (!next.configured) {
      setItems([]);
      setRows([]);
      return;
    }
    try {
      const catalog = await api.connections.catalog(search);
      setItems(catalog.items ?? []);
      setRows((await api.connections.list()).connections ?? []);
      setError("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setItems([]);
        setRows([]);
        return;
      }
      setError(err instanceof Error ? err.message : "Could not load apps.");
    }
  }

  async function save() {
    const apiKey = draft.trim();
    if (!apiKey) return;
    setBusy("save");
    try {
      setStatus(await api.connections.setKey(apiKey));
      setDraft("");
      setReplace(false);
      await refresh(query);
      onAppsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the key.");
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    setBusy("remove");
    try {
      await api.connections.clearKey();
      setStatus({ configured: false, lastFour: null });
      setItems([]);
      setRows([]);
      setReplace(false);
      setError("");
      onAppsChange?.();
    } finally {
      setBusy("");
    }
  }

  async function connect(slug: string) {
    setBusy(`connect-${slug}`);
    try {
      const started = await api.connections.begin(slug, window.location.origin);
      if (started.authorizationUrl) {
        window.open(started.authorizationUrl, "_blank", "noopener,noreferrer");
      }
      await refresh(query);
      onAppsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect that app.");
    } finally {
      setBusy("");
    }
  }

  async function finish(connectionId: string) {
    setBusy(`finish-${connectionId}`);
    try {
      await api.connections.complete(connectionId);
      await refresh(query);
      onAppsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish that app.");
    } finally {
      setBusy("");
    }
  }

  async function disconnect(connectionId: string) {
    setBusy(`disconnect-${connectionId}`);
    try {
      await api.connections.revoke(connectionId);
      await refresh(query);
      onAppsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disconnect that app.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div data-testid="plugins-pane">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-[16px] font-semibold text-paper">Plugins</h2>
        <button
          type="button"
          aria-label="Close Plugins"
          title="Close panel"
          onClick={onClose}
          className="inline-flex h-[34px] items-center gap-1.5 rounded-[8px] border border-hairline px-2.5 text-[13px] text-paper hover:bg-raised"
        >
          <IconClose />
          Close
        </button>
      </div>
      {showKeyField ? (
        <p className="mb-3 text-[13px] leading-5 text-mute">Paste a key to connect apps.</p>
      ) : (
        <p className="mb-3 text-[13px] leading-5 text-sage" data-testid="plugins-key-saved">
          Key saved{status?.lastFour ? ` · ••••${status.lastFour}` : ""}
        </p>
      )}
      {showKeyField ? (
        <label className="block text-[13px] text-mute" htmlFor="plugins-key">
          Plugins key
          <input
            id="plugins-key"
            data-testid="plugins-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            aria-label="Plugins key"
            className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {showKeyField ? (
          <Button
            type="button"
            variant="cream"
            size="sm"
            data-testid="plugins-save"
            disabled={!draft.trim() || busy === "save"}
            onClick={() => void save()}
          >
            {busy === "save" ? "Saving…" : "Save"}
          </Button>
        ) : (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="plugins-replace"
              onClick={() => setReplace(true)}
            >
              Replace
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="plugins-remove"
              disabled={busy === "remove"}
              onClick={() => void remove()}
            >
              Remove
            </Button>
          </>
        )}
      </div>
      {configured ? (
        <>
          <label className="mt-5 block text-[13px] text-mute" htmlFor="plugins-search">
            Search apps
            <input
              id="plugins-search"
              data-testid="plugins-search"
              aria-label="Search apps"
              className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper"
              value={query}
              onChange={(event) => {
                const next = event.target.value;
                setQuery(next);
                void refresh(next);
              }}
            />
          </label>
          <div className="mt-3 flex flex-col gap-2" data-testid="plugins-catalog">
            {items.map((item) => {
              const row = rows.find(
                (entry) => entry.provider === item.slug && entry.status !== "revoked",
              );
              return (
                <section
                  key={item.slug}
                  data-testid={`plugin-row-${item.slug}`}
                  className="rounded-[12px] border border-hairline bg-plate px-3 py-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-display text-[14.5px] text-paper">{item.name}</h3>
                    {row?.status === "connected" ? (
                      <span className="text-[12.5px] text-sage">Connected</span>
                    ) : null}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {row?.status === "connected" ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={busy === `disconnect-${row.id}`}
                        onClick={() => void disconnect(row.id)}
                      >
                        Disconnect
                      </Button>
                    ) : row?.status === "pending" ? (
                      <Button
                        type="button"
                        variant="cream"
                        size="sm"
                        disabled={busy === `finish-${row.id}`}
                        onClick={() => void finish(row.id)}
                      >
                        Finish
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="cream"
                        size="sm"
                        disabled={busy.startsWith("connect-")}
                        onClick={() => void connect(item.slug)}
                      >
                        Connect
                      </Button>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </>
      ) : null}
      {error ? (
        <p className="mt-3 text-[13px] text-danger" data-testid="plugins-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
