import { type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api";
import { openOwnerBrowser } from "../../lib/owner-browser";
import {
  filterPluginCatalog,
  pluginCatalogScrollAfterUpdate,
  pluginSearchShouldPreventDefault,
} from "../../lib/plugins-catalog";
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
  const catalogRef = useRef<HTMLDivElement>(null);
  const catalogScroll = useRef(0);
  const configured = Boolean(status?.configured);
  const ready = status !== null;
  const showKeyField = ready && (!configured || replace);

  useEffect(() => {
    void refresh();
  }, []);

  useLayoutEffect(() => {
    const node = catalogRef.current;
    if (!node) return;
    const max = node.scrollHeight - node.clientHeight;
    node.scrollTop = pluginCatalogScrollAfterUpdate(catalogScroll.current, max);
  }, [query, items]);

  async function refresh() {
    const next = await api.connections.status();
    setStatus(next);
    if (!next.configured) {
      setItems([]);
      setRows([]);
      return;
    }
    try {
      const catalog = await api.connections.catalog("");
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

  async function save(raw = draft) {
    const apiKey = raw.trim();
    if (!apiKey) {
      setError("Paste a key first.");
      return;
    }
    setBusy("save");
    try {
      setStatus(await api.connections.setKey(apiKey));
      setDraft("");
      setReplace(false);
      await refresh();
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
        openOwnerBrowser(started.authorizationUrl);
      }
      await refresh();
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
      await refresh();
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
      await refresh();
      onAppsChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disconnect that app.");
    } finally {
      setBusy("");
    }
  }

  function onSearchKey(event: KeyboardEvent<HTMLInputElement>) {
    if (!pluginSearchShouldPreventDefault(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
  }

  return (
    <div data-testid="plugins-pane" data-plugins-ready={ready ? "1" : "0"}>
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
      {!ready ? (
        <p className="mb-3 text-[13px] leading-5 text-mute">Checking the key…</p>
      ) : showKeyField ? (
        <p className="mb-3 text-[13px] leading-5 text-mute">Paste a key to connect apps.</p>
      ) : (
        <p className="mb-3 text-[13px] leading-5 text-sage" data-testid="plugins-key-saved">
          Key saved{status?.lastFour ? ` · ••••${status.lastFour}` : ""}
        </p>
      )}
      {showKeyField ? (
        <form
          className="block"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void save(String(data.get("api_key") || draft));
          }}
        >
          <label className="block text-[13px] text-mute" htmlFor="plugins-key">
            Plugins key
            <input
              id="plugins-key"
              name="api_key"
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
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="cream"
              size="sm"
              data-testid="plugins-save"
              disabled={busy === "save"}
            >
              {busy === "save" ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {showKeyField ? null : (
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
          <form
            className="mt-5 block"
            onSubmit={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            <label className="block text-[13px] text-mute" htmlFor="plugins-search">
              Search apps
              <input
                id="plugins-search"
                data-testid="plugins-search"
                type="search"
                enterKeyHint="search"
                aria-label="Search apps"
                placeholder="Search apps"
                className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper"
                value={query}
                onChange={(event) => setQuery(event.currentTarget.value)}
                onInput={(event) => setQuery(event.currentTarget.value)}
                onKeyDown={onSearchKey}
                onKeyUp={(event) => {
                  onSearchKey(event);
                  setQuery(event.currentTarget.value);
                }}
              />
            </label>
          </form>
          <div
            ref={catalogRef}
            className="mt-3 flex max-h-72 flex-col gap-2 overflow-y-auto"
            data-testid="plugins-catalog"
            onScroll={(event) => {
              catalogScroll.current = event.currentTarget.scrollTop;
            }}
          >
            {filterPluginCatalog(items, query).map((item) => {
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
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          void connect(item.slug);
                        }}
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
