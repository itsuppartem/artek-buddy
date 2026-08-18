import {
  type Dispatch,
  type MouseEvent,
  type SetStateAction,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { abortableDelay, api, isActive } from "../api";
import { isCronShape } from "../lib/cron";
import { isMemoryPath } from "../lib/memory";
import {
  computerLabel,
  embeddableScreenUrl,
  overlayPointerEvents,
  previewPointerEvents,
  screenIframeSandbox,
  shouldAutoBoot,
  shouldRefreshScreenUrl,
  shouldReplaceScreenUrl,
  shouldTakeControl,
} from "../lib/screen";
import {
  allowAlert,
  attentionFromBotChange,
  attentionFromEvent,
  isHistoricalEvent,
  shouldSendDesktopAlert,
  type AttentionAlert,
} from "../lib/alerts";
import { ChatMarkdown } from "../lib/chat-markdown";
import { stripMarkdown } from "../lib/markdown";
import {
  isComputerStatusEvent,
  isHiddenLiveDraft,
  isToolNoise,
  mergeThreadSnapshot,
  prependThreadMessagePage,
  reduceComputerStatus,
  reduceThreadSnapshot,
} from "../lib/thread-events";
import type {
  Bot,
  ComputerMode,
  ComputerStatus,
  ProductEvent,
  MemoryDocument,
  Routine,
  ThreadMessage,
  ThreadSnapshot,
} from "../types";
import { BotAvatar } from "../ui/bot-avatar";
import { Button } from "../ui/button";
import { WindowChrome } from "../ui/window-chrome";
import { BotContextMenu, type ContextMenuPosition } from "./BotContextMenu";
import { MessageContextMenu } from "./MessageContextMenu";

type Panel = "computer" | "settings" | "create" | null;

export function ShellPage() {
  const { botId } = useParams();
  const navigate = useNavigate();
  const [bots, setBots] = useState<Bot[]>([]);
  const [query, setQuery] = useState("");
  const [snapshot, setSnapshot] = useState<ThreadSnapshot | null>(null);
  const [draft, setDraft] = useState("");
  const [panel, setPanel] = useState<Panel>("computer");
  const [computer, setComputer] = useState<ComputerStatus | null>(null);
  const [screenUrl, setScreenUrl] = useState<string | null>(null);
  const screenUrlRef = useRef<string | null>(null);
  const [computerOpen, setComputerOpen] = useState(false);
  const [booting, setBooting] = useState(false);
  const autoBooted = useRef<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [later, setLater] = useState<string | null>(null);
  const [attention, setAttention] = useState<AttentionAlert | null>(null);
  const seenAlertKeys = useRef(new Set<string>());
  const recentKindAt = useRef(new Map<string, number>());
  const prevBotsRef = useRef(new Map<string, Bot>());
  const activeIdRef = useRef<string | undefined>(undefined);
  const botsRef = useRef<Bot[]>([]);
  const windowFocusedRef = useRef(true);
  const [contextMenu, setContextMenu] = useState<{
    bot: Bot;
    position: ContextMenuPosition;
  } | null>(null);
  const [messageMenu, setMessageMenu] = useState<{
    message: ThreadMessage;
    position: ContextMenuPosition;
  } | null>(null);
  const [replyTo, setReplyTo] = useState<ThreadMessage | null>(null);
  const expandedHistoryThread = useRef<string | null>(null);
  const messageScroll = useRef<HTMLDivElement>(null);

  const active = bots.find((bot) => bot.id === botId) ?? bots[0];
  const isBusy = Boolean(
    (snapshot?.run && isActive(snapshot.run.status)) ||
      (snapshot && (hasLive(snapshot) || hasActiveWorkers(snapshot))),
  );
  const otherBotIds = useMemo(
    () =>
      bots
        .map((bot) => bot.id)
        .filter((id) => id !== active?.id)
        .sort()
        .join("\0"),
    [bots, active?.id],
  );

  useEffect(() => {
    activeIdRef.current = active?.id;
    botsRef.current = bots;
  }, [active?.id, bots]);

  useEffect(() => {
    function syncFocus() {
      windowFocusedRef.current = document.visibilityState === "visible" && document.hasFocus();
    }
    syncFocus();
    window.addEventListener("focus", syncFocus);
    window.addEventListener("blur", syncFocus);
    document.addEventListener("visibilitychange", syncFocus);
    return () => {
      window.removeEventListener("focus", syncFocus);
      window.removeEventListener("blur", syncFocus);
      document.removeEventListener("visibilitychange", syncFocus);
    };
  }, []);

  function dispatchAlert(next: AttentionAlert, key: string, notifyOnFinish: boolean) {
    if (!allowAlert(next, notifyOnFinish)) return;
    if (seenAlertKeys.current.has(key)) return;
    const kindKey = `${next.botId}:${next.kind}`;
    const now = Date.now();
    const last = recentKindAt.current.get(kindKey) ?? 0;
    if (now - last < 8_000) {
      seenAlertKeys.current.add(key);
      return;
    }
    seenAlertKeys.current.add(key);
    recentKindAt.current.set(kindKey, now);
    if (seenAlertKeys.current.size > 250) {
      const oldest = seenAlertKeys.current.values().next().value;
      if (oldest) seenAlertKeys.current.delete(oldest);
    }
    const focused = windowFocusedRef.current && document.visibilityState === "visible";
    if (
      !shouldSendDesktopAlert({
        windowFocused: focused,
        viewingBotId: activeIdRef.current ?? null,
        alertBotId: next.botId,
      })
    ) {
      return;
    }
    void api.local.notify({
      title: next.title,
      body: next.body,
      urgency: next.urgency,
    });
    setAttention(next);
  }

  function considerEvent(incoming: ProductEvent, bot: Bot, subscribedAt: number) {
    if (isHistoricalEvent(incoming, subscribedAt)) return;
    const next = attentionFromEvent(incoming, bot.name);
    if (next) dispatchAlert(next, incoming.id, bot.notifyOnFinish);
  }

  async function refreshBots() {
    let list = await api.bots.list();
    if (list.length === 0) {
      list = [await api.bots.create({ name: "artek-buddy" })];
    }
    const prev = prevBotsRef.current;
    if (prev.size) {
      for (const next of list) {
        const before = prev.get(next.id);
        if (!before) continue;
        const alert = attentionFromBotChange(before, next);
        if (alert) {
          dispatchAlert(alert, `${next.id}:${alert.kind}:${next.updatedAt}`, next.notifyOnFinish);
        }
      }
    }
    prevBotsRef.current = new Map(list.map((item) => [item.id, item]));
    setBots(list);
    if (!botId || !list.some((bot) => bot.id === botId)) {
      navigate(list[0] ? `/app/${list[0].id}` : "/app", { replace: true });
    }
    return list;
  }

  function adoptScreenUrl(next: string | null) {
    const current = screenUrlRef.current;
    if (!shouldReplaceScreenUrl(current, next)) return;
    screenUrlRef.current = next;
    setScreenUrl(next);
  }

  async function ensureScreenUrl(id: string, available: boolean, force = false) {
    if (!available) {
      adoptScreenUrl(null);
      return;
    }
    if (!force && !shouldRefreshScreenUrl(screenUrlRef.current)) return;
    const screen = await api.computer.screenUrl(id).catch(() => ({ url: null }));
    adoptScreenUrl(embeddableScreenUrl(screen.url));
  }

  async function refreshThread(id: string) {
    const scrollElement = messageScroll.current;
    const stickToEnd =
      !scrollElement ||
      scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight < 80;
    const snap = await api.threads.get(id);
    setSnapshot((prev) =>
      mergeThreadSnapshot(prev, snap, expandedHistoryThread.current === snap.threadId),
    );
    setComputer(snap.computer);
    await ensureScreenUrl(id, snap.computer.screenAvailable);
    if (stickToEnd) {
      window.requestAnimationFrame(() => {
        const element = messageScroll.current;
        if (element) element.scrollTop = element.scrollHeight;
      });
    }
    return snap;
  }

  async function loadOlderMessages() {
    if (!active || snapshot?.olderCursor == null || loadingOlder) return;
    const scrollElement = messageScroll.current;
    const previousHeight = scrollElement?.scrollHeight ?? 0;
    setLoadingOlder(true);
    try {
      const page = await api.threads.messages(active.id, snapshot.olderCursor);
      expandedHistoryThread.current = page.threadId;
      setSnapshot((prev) => prependThreadMessagePage(prev, page));
      window.requestAnimationFrame(() => {
        const element = messageScroll.current;
        if (element) element.scrollTop += element.scrollHeight - previousHeight;
      });
    } finally {
      setLoadingOlder(false);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        await api.health();
        await refreshBots();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not reach the host");
      }
    })();
    const poll = window.setInterval(() => void refreshBots().catch(() => undefined), 4000);
    return () => window.clearInterval(poll);
  }, []);

  useEffect(() => {
    if (!active) return;
    screenUrlRef.current = null;
    setScreenUrl(null);
    expandedHistoryThread.current = null;
    const abort = new AbortController();
    const subscribedAt = Date.now();
    void (async () => {
      const snap = await refreshThread(active.id).catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Could not load thread");
        return null;
      });
      if (abort.signal.aborted) return;
      let after: string | null = null;
      let retryMs = 250;
      while (!abort.signal.aborted) {
        try {
          for await (const event of api.threads.subscribe(active.id, after, abort.signal)) {
            if (abort.signal.aborted) break;
            after = event.id;
            retryMs = 250;
            applyThreadEvent(event, setSnapshot, setComputer);
            const bot = botsRef.current.find((item) => item.id === active.id) ?? active;
            considerEvent(event, bot, subscribedAt);
            if (event.type === "run.completed" || event.type === "run.failed") {
              void refreshBots().catch(() => undefined);
              void refreshThread(active.id).catch(() => undefined);
            }
          }
        } catch {
          // Reconnect after a dropped stream. The last event id keeps replay safe.
        }
        if (abort.signal.aborted) break;
        await refreshThread(active.id).catch(() => null);
        try {
          await abortableDelay(retryMs, abort.signal);
        } catch {
          break;
        }
        retryMs = Math.min(retryMs * 2, 5_000);
      }
    })();
    return () => abort.abort();
  }, [active?.id]);

  useEffect(() => {
    const ids = otherBotIds ? otherBotIds.split("\0") : [];
    if (!ids.length) return;
    const abort = new AbortController();
    const subscribedAt = Date.now();
    for (const id of ids) {
      void (async () => {
        let after: string | null = null;
        let retryMs = 250;
        while (!abort.signal.aborted) {
          try {
            for await (const event of api.threads.subscribe(id, after, abort.signal)) {
              if (abort.signal.aborted) break;
              after = event.id;
              retryMs = 250;
              const bot = botsRef.current.find((item) => item.id === id);
              if (bot) considerEvent(event, bot, subscribedAt);
            }
          } catch {
            // Same reconnect as the active thread stream.
          }
          if (abort.signal.aborted) break;
          try {
            await abortableDelay(retryMs, abort.signal);
          } catch {
            break;
          }
          retryMs = Math.min(retryMs * 2, 5_000);
        }
      })();
    }
    return () => abort.abort();
  }, [otherBotIds]);

  useEffect(() => {
    setReplyTo(null);
    setMessageMenu(null);
  }, [active?.id]);

  useEffect(() => {
    if (panel !== "computer") {
      autoBooted.current = null;
      return;
    }
    if (!active) return;
    if (computer?.state === "booting") return;
    if (!shouldAutoBoot(computer?.state, screenUrl, autoBooted.current === active.id)) return;
    autoBooted.current = active.id;
    void bootComputer({
      takeControl: false,
      overlay: false,
      force: true,
    });
  }, [panel, active?.id, computer?.state, screenUrl]);

  useEffect(() => {
    setComputerOpen(false);
  }, [active?.id]);

  useEffect(() => {
    if ((panel !== "computer" && !computerOpen) || !active || computer?.state !== "running") return;
    const ping = () => void api.computer.heartbeat(active.id).catch(() => undefined);
    ping();
    const timer = window.setInterval(ping, 60_000);
    return () => window.clearInterval(timer);
  }, [panel, computerOpen, active?.id, computer?.state]);

  useEffect(() => {
    if (!computerOpen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setComputerOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [computerOpen]);

  const filtered = useMemo(
    () => bots.filter((bot) => `${bot.name} ${stripMarkdown(bot.preview || bot.title)}`.toLowerCase().includes(query.toLowerCase())),
    [bots, query],
  );

  async function send(textOverride?: string) {
    const text = (textOverride ?? draft).trim();
    if (!active || !text) return;
    const replyId = replyTo?.id ?? null;
    if (textOverride == null) setDraft("");
    setError(null);
    try {
      await api.threads.send(active.id, text, replyId);
      setReplyTo(null);
      await refreshThread(active.id);
    } catch (err) {
      if (textOverride == null) setDraft(text);
      setError(err instanceof Error ? err.message : "Send failed");
    }
  }

  async function stop() {
    if (!active) return;
    try {
      await api.threads.stop(active.id);
      await refreshThread(active.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    }
  }

  async function bootComputer({
    takeControl,
    overlay,
    force = false,
  }: {
    takeControl: boolean;
    overlay: boolean;
    force?: boolean;
  }) {
    if (!active) return;
    const needsBoot = force || computer?.state !== "running" || !screenUrl;
    if (overlay && needsBoot) setBooting(true);
    try {
      if (needsBoot) {
        const status = await api.computer.boot(active.id);
        setComputer(status);
      }
      if (takeControl) {
        await api.computer.takeover(active.id);
        setComputer(await api.computer.status(active.id));
      }
      await ensureScreenUrl(active.id, true, true);
    } catch (err) {
      setLater(err instanceof Error ? err.message : "Could not boot the computer");
    } finally {
      setBooting(false);
    }
  }

  async function openOverlay(source: "preview" | "button") {
    if (!active) return;
    await bootComputer({
      takeControl: shouldTakeControl(source),
      overlay: computer?.state !== "running",
      force: computer?.state !== "running",
    });
    setComputerOpen(true);
  }

  async function releaseComputer() {
    if (!active) return;
    await api.computer.release(active.id).catch(() => undefined);
    const status = await api.computer.status(active.id).catch(() => null);
    if (status) setComputer(status);
    await ensureScreenUrl(active.id, true, true);
  }

  async function createBot(input: {
    name: string;
    title: string;
    description: string;
    computerMode: ComputerMode;
  }) {
    const bot = await api.bots.create({
      name: input.name.trim(),
      title: input.title,
      description: input.description,
      instructions: input.description,
      computerMode: input.computerMode,
    });
    await refreshBots();
    navigate(`/app/${bot.id}`);
    setPanel("computer");
  }

  async function deleteBot(bot: Bot, deleteMemories: boolean = false) {
    try {
      await api.bots.remove(bot.id, deleteMemories);
      setPanel(null);
      setSnapshot(null);
      const list = await refreshBots();
      if (active?.id === bot.id) {
        const remaining = list.filter((b) => b.id !== bot.id);
        if (remaining[0]) navigate(`/app/${remaining[0].id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete chat");
    }
  }

  useEffect(() => {
    if (!later) return;
    const timer = window.setTimeout(() => setLater(null), 2400);
    return () => window.clearTimeout(timer);
  }, [later]);

  useEffect(() => {
    if (!attention || active?.id !== attention.botId) return;
    if (windowFocusedRef.current && document.visibilityState === "visible") {
      setAttention(null);
    }
  }, [active?.id, attention]);

  return (
    <div className="relative flex h-full min-w-0 overflow-hidden bg-[#050506] text-[#DFDFE2]">
      <aside className="flex w-[316px] shrink-0 flex-col border-r border-[#171719] bg-[#0B0B0C]">
        <div className="app-drag flex items-center justify-between px-[18px] pb-3 pt-4">
          <WindowChrome />
          <button
            type="button"
            onClick={() => setPanel("create")}
            className="app-no-drag text-[21px] text-[#7A7A80] hover:text-[#C9C9CE]"
            title="New bot"
            aria-label="New bot"
          >
            +
          </button>
        </div>
        <div className="mx-3.5 mb-3 flex items-center gap-2.5 rounded-xl border border-[#202023] bg-[#141416] px-3 py-2 text-[14px] text-[#6C6C70]">
          <span>⌕</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
            className="w-full bg-transparent outline-none"
          />
        </div>
        <div className="ab-scroll flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 pb-2.5">
          {filtered.map((bot) => (
            <button
              key={bot.id}
              type="button"
              onClick={() => navigate(`/app/${bot.id}`)}
              onContextMenu={(event) => {
                event.preventDefault();
                setContextMenu({
                  bot,
                  position: { x: event.clientX, y: event.clientY },
                });
              }}
              className="flex gap-3 rounded-xl px-2.5 py-[11px] text-left"
              style={{ background: active?.id === bot.id ? "#161618" : "transparent" }}
            >
              <BotAvatar color={bot.color} size={38} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span
                    className={`flex items-center gap-1.5 text-[15px] text-[#ECECEE] ${
                      bot.unread ? "font-semibold" : "font-medium"
                    }`}
                  >
                    {bot.name}
                    {bot.pinned ? (
                      <span title="Pinned" className="text-[11px] text-[#A8A8AD]">
                        📌
                      </span>
                    ) : null}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] text-[#6C6C70]">
                    {bot.status === "idle" ? "" : bot.status}
                    {bot.unread ? (
                      <span
                        aria-hidden="true"
                        className="inline-block h-2 w-2 rounded-full bg-[#8B5CF6]"
                      />
                    ) : null}
                  </span>
                </div>
                <div
                  className={`mt-0.5 truncate text-[13.5px] ${
                    bot.unread ? "font-medium text-[#C9C9CE]" : "text-[#85858A]"
                  }`}
                >
                  {stripMarkdown(bot.preview || bot.title)}
                </div>
              </div>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setLater("Plugins ship with a later stage.")}
          className="mx-3 mb-1 flex items-center gap-3 rounded-[11px] px-2.5 py-2 hover:bg-[#131315]"
        >
          <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-[#17171A] text-[#9A9AA0]">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M4 7h3a1 1 0 0 0 1-1 1.5 1.5 0 1 1 3 0 1 1 0 0 0 1 1h3v3a1 1 0 0 0 1 1 1.5 1.5 0 1 1 0 3 1 1 0 0 0-1 1v3h-3a1 1 0 0 0-1 1 1.5 1.5 0 1 1-3 0 1 1 0 0 0-1-1H4v-3a1 1 0 0 0-1-1 1.5 1.5 0 1 1 0-3 1 1 0 0 0 1-1z" />
            </svg>
          </span>
          <span className="text-[14.5px] text-[#C9C9CE]">Plugins</span>
        </button>
        <div className="flex items-center gap-[11px] px-[18px] py-3.5">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-[#232326] text-[12px] text-[#A8A8AD]">
            Y
          </span>
          <span className="text-[14.5px] text-[#C9C9CE]">You</span>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-[#0D0D0E]">
        <div className="flex items-center justify-between border-b border-[#141416] px-[22px] py-[17px]">
          <button
            type="button"
            onClick={() => setPanel("settings")}
            className="flex min-w-0 items-center gap-3"
          >
            {active ? <BotAvatar color={active.color} size={26} /> : null}
            <span className="min-w-0">
              <span className="block truncate text-[16px] font-medium text-[#ECECEE]">
                {active?.name ?? "Select a bot"}
              </span>
            </span>
          </button>
          <button
            type="button"
            title="Agent computer"
            onClick={() => setPanel((current) => (current === "computer" ? null : "computer"))}
            className="grid h-[30px] w-[34px] place-items-center rounded-[9px] hover:bg-[#1B1B1E]"
            style={{ background: panel ? "#1B1B1E" : "transparent" }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A8A8AD" strokeWidth="1.6">
              <rect x="2" y="4" width="20" height="13" rx="2" />
              <path d="M8 21h8M12 17v4" />
            </svg>
          </button>
        </div>
        <div
          ref={messageScroll}
          data-testid="thread"
          className="ab-scroll flex flex-1 flex-col gap-[13px] overflow-y-auto px-7 py-6"
        >
          {error ? <div className="self-center text-[13.5px] text-[#E65707]">{error}</div> : null}
          {snapshot?.olderCursor != null ? (
            <button
              type="button"
              disabled={loadingOlder}
              onClick={() => void loadOlderMessages()}
              className="self-center rounded-lg px-3 py-1.5 text-[13px] text-[#85858A] hover:bg-[#1A1A1D] hover:text-[#C9C9CE] disabled:opacity-50"
            >
              {loadingOlder ? "Loading…" : "Load earlier messages"}
            </button>
          ) : null}
          {(snapshot?.messages ?? [])
            .filter((message) => !isToolNoise(message) && !isHiddenLiveDraft(message))
            .map((message) => (
            <MessageView
              key={message.id}
              botId={active?.id ?? ""}
              canAnswer
              message={message}
              onAnswer={(text) => send(text)}
              onOpenBot={(id) => navigate(`/app/${id}`)}
              onSubagentChange={() => {
                if (active) void refreshThread(active.id);
              }}
              onContextMenu={(event, item) => {
                event.preventDefault();
                setMessageMenu({ message: item, position: { x: event.clientX, y: event.clientY } });
              }}
            />
          ))}
          {snapshot?.run && isActive(snapshot.run.status) ? (
            <div className="flex justify-start">
              <div
                className="flex items-center gap-1.5 rounded-[18px] bg-[#161619] border border-[#222226] px-4 py-3"
                title="Typing…"
              >
                <span className="inline-block h-2 w-2 rounded-full bg-[#C45C26] animate-pulse" />
                <span
                  className="inline-block h-2 w-2 rounded-full bg-[#C45C26] animate-pulse"
                  style={{ animationDelay: "150ms" }}
                />
                <span
                  className="inline-block h-2 w-2 rounded-full bg-[#C45C26] animate-pulse"
                  style={{ animationDelay: "300ms" }}
                />
              </div>
            </div>
          ) : null}
        </div>
        <div className="px-6 pb-6 pt-3">
          {replyTo ? (
            <div className="mb-2 flex items-center gap-3 rounded-[16px] border border-[#202023] bg-[#131315] px-3.5 py-2">
              <div className="min-w-0 flex-1">
                <div className="text-[12px] text-[#85858A]">
                  Replying to {replyTo.role === "bot" ? active?.name || "bot" : "you"}
                </div>
                <div className="truncate text-[13.5px] text-[#C9C9CE]">{replyExcerpt(replyTo)}</div>
              </div>
              <button
                type="button"
                className="text-[16px] text-[#85858A] hover:text-[#ECECEE]"
                aria-label="Cancel reply"
                onClick={() => setReplyTo(null)}
              >
                ✕
              </button>
            </div>
          ) : null}
          <div className="flex items-center gap-3.5 rounded-full border border-[#202023] bg-[#131315] py-[9px] pr-2.5 pl-3">
            <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full border border-[#26262A] text-[18px] text-[#9A9AA0]">
              +
            </span>
            <input
              value={draft}
              aria-label="Message"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder={
                replyTo ? "Write a reply…" : active ? `Message ${active.name}` : "Message…"
              }
              className="flex-1 bg-transparent text-[15.5px] text-[#E9E9EA] outline-none"
            />
            {isBusy ? (
              <button
                type="button"
                aria-label="Stop"
                onClick={() => void stop()}
                className="grid h-9 w-9 place-items-center rounded-full bg-[#E65707] text-white hover:bg-[#D44E06]"
                title="Stop the lead and workers"
              >
                ■
              </button>
            ) : null}
            <button
              type="button"
              aria-label="Send"
              disabled={!draft.trim()}
              onClick={() => void send()}
              className="grid h-9 w-9 place-items-center rounded-full bg-[#F1F1EF] text-[#17171A] disabled:opacity-40"
            >
              ↑
            </button>
          </div>
        </div>
      </main>

      <aside
        className={`flex h-full min-h-0 shrink-0 flex-col overflow-hidden bg-[#0A0A0B] transition-[width] duration-200 ease-out ${
          panel ? "w-[384px] border-l border-[#141416]" : "w-0"
        }`}
      >
        {panel ? (
          <div className="ab-scroll h-full w-[384px] overflow-y-auto px-5 py-[17px]">
            {panel === "create" ? (
              <CreateBotForm onCancel={() => setPanel(null)} onCreate={(input) => void createBot(input)} />
            ) : null}
            {panel === "settings" && active ? (
              <BotSettings
                bot={active}
                onClose={() => setPanel(null)}
                onUpdated={() => void refreshBots()}
                onDelete={(deleteMemories) => void deleteBot(active, deleteMemories)}
                onLater={setLater}
              />
            ) : null}
            {panel === "computer" && active ? (
              <ComputerPane
                bot={active}
                computer={computer ?? snapshot?.computer ?? null}
                screenUrl={screenUrl}
                booting={booting}
                onClose={() => setPanel(null)}
                onSettings={() => setPanel("settings")}
                onOpenFullscreen={() => void openOverlay("preview")}
                onTakeControl={() => void openOverlay("button")}
                onRelease={() => void releaseComputer()}
                onLater={setLater}
              />
            ) : null}
          </div>
        ) : null}
      </aside>

      {messageMenu ? (
        <MessageContextMenu
          position={messageMenu.position}
          onClose={() => setMessageMenu(null)}
          onReply={() => {
            setReplyTo(messageMenu.message);
            setMessageMenu(null);
          }}
        />
      ) : null}

      {contextMenu ? (
        <BotContextMenu
          bot={contextMenu.bot}
          position={contextMenu.position}
          onClose={() => setContextMenu(null)}
          onTogglePinned={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              await api.bots.update(target.id, { pinned: !target.pinned });
              await refreshBots();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Failed to update pin");
            }
          }}
          onToggleUnread={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              if (target.unread) {
                await api.threads.markRead(target.id);
              } else {
                await api.threads.markUnread(target.id);
              }
              await refreshBots();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Failed to toggle read status");
            }
          }}
          onEdit={() => {
            const target = contextMenu.bot;
            setContextMenu(null);
            navigate(`/app/${target.id}`);
            setPanel("settings");
          }}
          onDuplicate={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              const duplicated = await api.bots.duplicate(target.id);
              await refreshBots();
              navigate(`/app/${duplicated.id}`);
            } catch (err) {
              setError(err instanceof Error ? err.message : "Duplicate failed");
            }
          }}
          onArchive={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              await api.bots.archive(target.id);
              const list = await refreshBots();
              if (active?.id === target.id) {
                const remaining = list.filter((b) => b.id !== target.id);
                if (remaining[0]) navigate(`/app/${remaining[0].id}`);
              }
            } catch (err) {
              setError(err instanceof Error ? err.message : "Archive failed");
            }
          }}
          onDelete={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              await api.bots.remove(target.id, false);
              const list = await refreshBots();
              if (active?.id === target.id) {
                const remaining = list.filter((b) => b.id !== target.id);
                if (remaining[0]) navigate(`/app/${remaining[0].id}`);
              }
            } catch (err) {
              setError(err instanceof Error ? err.message : "Delete failed");
            }
          }}
        />
      ) : null}

      {attention || later ? (
        <div className="absolute bottom-6 left-1/2 z-20 flex -translate-x-1/2 flex-col items-center gap-2">
          {attention ? (
            <button
              type="button"
              data-testid="attention-alert"
              onClick={() => {
                navigate(`/app/${attention.botId}`);
                setAttention(null);
              }}
              className="max-w-[min(480px,90vw)] rounded-full bg-[#1A1A1D] px-4 py-2 text-left text-[13.5px] text-[#C9C9CE] shadow-[0_12px_40px_rgba(0,0,0,.45)] hover:bg-[#222226]"
            >
              <span className="font-medium text-[#ECECEE]">{attention.title}</span>
              {attention.body ? (
                <span className="mt-0.5 block truncate text-[12.5px] text-[#85858A]">{attention.body}</span>
              ) : null}
            </button>
          ) : null}
          {later ? (
            <div className="rounded-full bg-[#1A1A1D] px-4 py-2 text-[13.5px] text-[#C9C9CE] shadow-[0_12px_40px_rgba(0,0,0,.45)]">
              {later}
            </div>
          ) : null}
        </div>
      ) : null}

      {booting ? (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-[22px] bg-[rgba(4,4,5,.96)]">
          <div className="text-[19px] font-medium text-[#F1F1F2]">
            Booting up {active ? computerLabel(computer?.mode || active.computerMode, active.name) : "computer"}
          </div>
          <div className="h-[5px] w-[min(420px,70%)] overflow-hidden rounded-full bg-[#232327]">
            <div className="h-full w-2/3 rounded-full bg-[#F1F1EF]" />
          </div>
        </div>
      ) : computerOpen && active ? (
        <div className="absolute inset-0 z-30 flex flex-col bg-[#050506]">
          <div className="flex items-center justify-between gap-4 border-b border-[#171719] px-[18px] py-3.5">
            <div className="flex min-w-0 items-center gap-3">
              <BotAvatar color={active.color} size={28} />
              <span className="truncate text-[15.5px] font-medium text-[#ECECEE]">
                {computerLabel(computer?.mode || active.computerMode, active.name)}
              </span>
              {computer?.controlHolder === "user" ? (
                <span className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]">
                  You have control
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-3">
              {computer?.controlHolder === "user" ? (
                <Button type="button" variant="outline" size="sm" onClick={() => void releaseComputer()}>
                  Release
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void bootComputer({ takeControl: true, overlay: false })}
                >
                  Take control
                </Button>
              )}
              <button
                type="button"
                className="text-[16px] text-[#85858A] hover:text-[#ECECEE]"
                aria-label="Close computer"
                onClick={() => setComputerOpen(false)}
              >
                ✕
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 bg-[#0E0E10]">
            {computer?.state === "running" && embeddableScreenUrl(screenUrl) ? (
              <iframe
                title="Bot screen"
                src={embeddableScreenUrl(screenUrl) ?? undefined}
                sandbox={screenIframeSandbox(screenUrl)}
                className="h-full w-full border-0 bg-black"
                allow="clipboard-read; clipboard-write; fullscreen"
                style={{ pointerEvents: overlayPointerEvents(computer?.controlHolder) }}
              />
            ) : (
              <div className="grid h-full place-items-center text-sm text-[#6C6C70]">
                {computer?.state === "suspended" ? "Computer is asleep" : computerLabel(computer?.mode, active.name)}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function applyThreadEvent(
  event: ProductEvent,
  setSnapshot: Dispatch<SetStateAction<ThreadSnapshot | null>>,
  setComputer: Dispatch<SetStateAction<ComputerStatus | null>>,
) {
  if (
    event.type === "thread.progress" ||
    event.type === "thread.message.created" ||
    event.type === "thread.message.updated" ||
    event.type === "thread.meta" ||
    event.type === "thread.subagent" ||
    event.type === "thread.computer" ||
    event.type === "bot.spawned" ||
    event.type === "agent.tool.called" ||
    event.type === "run.started" ||
    event.type === "run.waiting_input" ||
    event.type === "run.completed" ||
    event.type === "run.failed" ||
    event.type === "run.cancelled"
  ) {
    setSnapshot((prev) => reduceThreadSnapshot(prev, event));
  }
  if (isComputerStatusEvent(event)) {
    setComputer((prev) => reduceComputerStatus(prev, event));
  }
}

function hasLive(snapshot: ThreadSnapshot): boolean {
  return snapshot.messages.some(
    (message) =>
      message.id.startsWith("stream:") &&
      message.blocks.some((b) => b.kind === "progress" && Boolean(b.text)),
  );
}

function hasActiveWorkers(snapshot: ThreadSnapshot): boolean {
  if ((snapshot.subagents ?? []).some((item) => item.status === "queued" || item.status === "running")) {
    return true;
  }
  return snapshot.messages.some((message) =>
    message.blocks.some(
      (block) =>
        block.kind === "subagent" && (block.status === "queued" || block.status === "running"),
    ),
  );
}

function replyExcerpt(message: ThreadMessage): string {
  if (message.replyTo?.excerpt) return message.replyTo.excerpt;
  const text = message.blocks.find((block) => "text" in block && block.text);
  return text && "text" in text ? text.text : "Message";
}

function MessageView({
  botId,
  canAnswer,
  message,
  onAnswer,
  onOpenBot,
  onSubagentChange,
  onContextMenu,
}: {
  botId: string;
  canAnswer: boolean;
  message: ThreadMessage;
  onAnswer: (text: string) => Promise<void>;
  onOpenBot: (botId: string) => void;
  onSubagentChange?: () => void;
  onContextMenu?: (event: MouseEvent, message: ThreadMessage) => void;
}) {
  const quote = message.replyTo;
  return (
    <div
      onContextMenu={(event) => {
        if (!onContextMenu) return;
        event.preventDefault();
        onContextMenu(event, message);
      }}
    >
      {quote ? (
        <div className={`mb-1 flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
          <div className="max-w-[70%] border-l-2 border-[#3D3D42] pl-2.5 text-[13px] leading-[1.4] text-[#85858A]">
            {stripMarkdown(quote.excerpt)}
          </div>
        </div>
      ) : null}
      {message.blocks.map((block, index) => {
        if (block.kind === "meta") {
          return (
            <div
              key={index}
              className="flex items-center justify-center gap-2 py-1 text-[13.5px] text-[#85858A]"
            >
              <span className="text-[#E65707]">◷</span>
              <span>{block.text}</span>
            </div>
          );
        }
        if (block.kind === "progress") {
          if (isHiddenLiveDraft(message)) {
            return null;
          }
          return (
            <div key={index} className="flex justify-start">
              <div className="max-w-[74%] rounded-[20px] bg-[#1A1A1D] px-[18px] py-3 text-[15.5px] leading-[1.5] text-[#DFDFE2]">
                <ChatMarkdown streaming>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        if (block.kind === "subagent") {
          const running = block.status === "queued" || block.status === "running";
          const failed = block.status === "failed" || block.status === "cancelled";
          const label = block.index ? `#${block.index} ${block.name}` : block.name;
          return (
            <div
              key={index}
              className="max-w-[74%] min-w-[340px] w-fit rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[15px] font-medium text-[#ECECEE]">{label}</span>
                <span
                  className="rounded-full px-[11px] py-1 text-[13px]"
                  style={{
                    background: failed
                      ? "rgba(230,87,7,.14)"
                      : running
                        ? "rgba(245,160,60,.14)"
                        : "rgba(48,162,75,.14)",
                    color: failed ? "#E65707" : running ? "#D4A017" : "#4ECB71",
                    animation: running ? "abPulse 1.2s ease-in-out infinite" : undefined,
                  }}
                >
                  {block.status}
                </span>
              </div>
              <div className="mt-2 text-[13.5px] text-[#85858A]">{block.task}</div>
              {block.clarifications ? (
                <div className="mt-2 text-[13px] leading-[1.45] text-[#9A9AA0]">
                  {block.clarifications}
                </div>
              ) : null}
              {block.progress || block.result ? (
                <div className="mt-2.5 text-[14.5px] leading-[1.5] text-[#A8A8AD]">
                  <ChatMarkdown streaming={running}>
                    {block.result || block.progress || ""}
                  </ChatMarkdown>
                </div>
              ) : null}
              {botId && block.agentId ? (
                <div className="mt-3 flex gap-2">
                  {running ? (
                    <button
                      type="button"
                      className="rounded-full bg-[#2A1510] px-3 py-1 text-[13px] text-[#E65707] hover:bg-[#3A1C14]"
                      onClick={() => {
                        void api.subagents
                          .stop(botId, block.agentId)
                          .then(() => onSubagentChange?.())
                          .catch(() => undefined);
                      }}
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="rounded-full bg-[#1B1B1E] px-3 py-1 text-[13px] text-[#C9C9CE] hover:bg-[#242428]"
                      onClick={() => {
                        void api.subagents
                          .restart(botId, block.agentId)
                          .then(() => onSubagentChange?.())
                          .catch(() => undefined);
                      }}
                    >
                      Restart
                    </button>
                  )}
                </div>
              ) : null}
            </div>
          );
        }
        if (block.kind === "child_bot") {
          const removed = block.status === "deleted" || block.status === "archived";
          return (
            <button
              key={index}
              type="button"
              disabled={removed}
              onClick={() => onOpenBot(block.botId)}
              className="w-[min(340px,90%)] rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4 text-left disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-[#ECECEE]">{block.name}</span>
                <span className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]">
                  {block.status}
                </span>
              </div>
              {block.title ? (
                <div className="mt-2 text-[14.5px] leading-[1.5] text-[#A8A8AD]">
                  {block.title}
                </div>
              ) : null}
            </button>
          );
        }
        if (block.kind === "text" && message.role === "user") {
          return (
            <div key={index} className="flex justify-end">
              <div className="max-w-[70%] rounded-[20px] bg-[#F1F1EF] px-[18px] py-3 text-[15.5px] leading-[1.45] text-[#1A1A1A]">
                {block.text}
              </div>
            </div>
          );
        }
        if (block.kind === "text") {
          return (
            <div key={index} className="flex justify-start">
              <div className="max-w-[74%] rounded-[20px] bg-[#1A1A1D] px-[18px] py-3 text-[15.5px] leading-[1.5] text-[#DFDFE2]">
                <ChatMarkdown>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        if (block.kind === "card") {
          return (
            <div key={index} className="flex justify-start">
              <div className="flex flex-col gap-2 rounded-[20px] bg-[#1A1A1D] px-5 py-4">
                {block.lines.map((line) => (
                  <div key={line.k} className="flex items-baseline gap-2.5 text-[15px]">
                    <span className="text-[#30A24B]">✓</span>
                    <span className="font-semibold text-white">{line.k}</span>
                    <span className="text-[#85858A]">→</span>
                    <span>{line.v}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        }
        if (block.kind === "ask") {
          return (
            <AskCard
              key={index}
              block={block}
              canAnswer={canAnswer}
              onAnswer={onAnswer}
            />
          );
        }
        if (block.kind === "computer") {
          return (
            <div
              key={index}
              className="w-[340px] rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-[#ECECEE]">Tool</span>
                <span className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]">
                  {block.state}
                </span>
              </div>
              <div className="my-2.5 text-[14.5px] leading-[1.5] text-[#A8A8AD]">
                <ChatMarkdown>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

type AskBlock = Extract<ThreadMessage["blocks"][number], { kind: "ask" }>;

function AskCard({
  block,
  canAnswer,
  onAnswer,
}: {
  block: AskBlock;
  canAnswer: boolean;
  onAnswer: (text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submitAnswer(value: string) {
    const text = value.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    try {
      await onAnswer(text);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[74%] rounded-[20px] border border-[#242428] bg-[#141417] px-5 py-[17px]">
      <div className="text-[15.5px] leading-[1.5] text-[#ECECEE]">
        <ChatMarkdown>{block.text}</ChatMarkdown>
      </div>
      {block.detail ? (
        <pre className="mt-3 rounded-xl bg-[#0E0E10] px-3.5 py-3 font-mono text-[12.5px] leading-[1.7] text-[#85858A]">
          {block.detail}
        </pre>
      ) : null}
      {block.status === "answered" ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-[#4ECB71]">
          {block.answer ? `Answered: ${block.answer}` : "Answered"}
        </div>
      ) : !canAnswer ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-[#85858A]">No longer active</div>
      ) : editing ? (
        <form
          className="mt-3.5 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submitAnswer(answer);
          }}
        >
          <input
            aria-label="Answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Type your answer"
            className="rounded-[11px] border border-[#303035] bg-[#0E0E10] px-3.5 py-2.5 text-[14.5px] text-[#ECECEE] outline-none focus:border-[#66666D]"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={!answer.trim() || submitting}
              className="rounded-[11px] bg-[#F1F1EF] px-[17px] py-2 text-[14.5px] font-medium text-[#17171A] disabled:opacity-50"
            >
              {submitting ? "Sending…" : "Send answer"}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => {
                setAnswer("");
                setEditing(false);
              }}
              className="rounded-[11px] border border-[#26262A] px-[17px] py-2 text-[14.5px] text-[#C9C9CE] disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="mt-3.5">
          {block.actions && block.actions.length > 0 ? (
            <div className="flex flex-col gap-2">
              {block.actions.map((act, i) => {
                const letter = String.fromCharCode(65 + (i % 26));
                return (
                  <button
                    key={act.id}
                    type="button"
                    disabled={submitting}
                    onClick={() => void submitAnswer(act.label)}
                    className="group flex w-full items-center rounded-[12px] border border-[#242429] bg-[#17171B] px-3.5 py-2.5 text-left transition hover:border-[#383842] hover:bg-[#1E1E23] disabled:opacity-50"
                  >
                    <span className="mr-3 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#232328] text-[12px] font-semibold text-[#8E8E94] group-hover:bg-[#2A2A30] group-hover:text-[#DFDFE2]">
                      {letter}
                    </span>
                    <span className="text-[14px] leading-[1.4] text-[#DFDFE2] group-hover:text-white">
                      {act.label}
                    </span>
                  </button>
                );
              })}
              <button
                type="button"
                disabled={submitting}
                onClick={() => setEditing(true)}
                className="mt-1 self-start text-[13px] text-[#85858A] hover:text-[#C9C9CE] disabled:opacity-50"
              >
                Type custom reply…
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={() => void submitAnswer("approved")}
                className="rounded-[11px] bg-[#F1F1EF] px-[17px] py-2 text-[14.5px] font-medium text-[#17171A] disabled:opacity-50"
              >
                {submitting ? "Sending…" : "Send it"}
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setEditing(true)}
                className="rounded-[11px] border border-[#26262A] px-[17px] py-2 text-[14.5px] text-[#C9C9CE] disabled:opacity-50"
              >
                Edit first
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ComputerModePicker({
  value,
  onChange,
}: {
  value: ComputerMode;
  onChange: (value: ComputerMode) => void;
}) {
  return (
    <div className="mt-4">
      <div className="text-[14px] text-[#85858A]">Computer</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["team", "dedicated"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={value === mode}
            onClick={() => onChange(mode)}
            className={`rounded-[11px] border px-3.5 py-3 text-[14px] capitalize ${
              value === mode
                ? "border-[#6C6C70] bg-[#1A1A1D] text-[#ECECEE]"
                : "border-[#26262A] text-[#85858A]"
            }`}
          >
            {mode === "team" ? "Team" : "Private"}
          </button>
        ))}
      </div>
    </div>
  );
}

function CreateBotForm({
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
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13.5px] text-[#85858A]">New bot</span>
        <button type="button" onClick={onCancel}>
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
        type="button"
        disabled={!name.trim()}
        onClick={() => onCreate({ name, title, description, computerMode })}
        className="mt-5 rounded-[11px] bg-[#F1F1EF] px-4 py-2 text-[#17171A] disabled:opacity-40"
      >
        Create
      </button>
    </div>
  );
}

function BotSettings({
  bot,
  onClose,
  onUpdated,
  onDelete,
  onLater,
}: {
  bot: Bot;
  onClose: () => void;
  onUpdated: () => void;
  onDelete: (deleteMemories: boolean) => void;
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
          <div>
            <label className="text-[12px] text-[#85858A]">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </div>
          <div>
            <label className="text-[12px] text-[#85858A]">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Code Reviewer"
              className="mt-1 w-full rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </div>
          <div>
            <label className="text-[12px] text-[#85858A]">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 w-full resize-none rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </div>
          <div>
            <label className="text-[12px] text-[#85858A]">Instructions (Prompt)</label>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={4}
              className="mt-1 w-full resize-none rounded-lg border border-[#26262A] bg-[#141416] px-3 py-1.5 text-[14px] text-[#ECECEE] outline-none"
            />
          </div>
          <div className="mt-2 flex gap-2">
            <Button type="button" size="sm" disabled={saving || !name.trim()} onClick={() => void save()}>
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
          <div className="mt-3">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(true)}>
              Edit Profile
            </Button>
          </div>
        </>
      )}

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

function ComputerPane({
  bot,
  computer,
  screenUrl,
  booting,
  onClose,
  onSettings,
  onOpenFullscreen,
  onTakeControl,
  onRelease,
  onLater,
}: {
  bot: Bot;
  computer: ComputerStatus | null;
  screenUrl: string | null;
  booting: boolean;
  onClose: () => void;
  onSettings: () => void;
  onOpenFullscreen: () => void;
  onTakeControl: () => void;
  onRelease: () => void;
  onLater: (text: string) => void;
}) {
  const mode = computer?.mode || bot.computerMode;
  const label = computerLabel(mode, bot.name);
  const preview = embeddableScreenUrl(screenUrl);
  const isRunning = computer?.state === "running";
  const isBooting = booting || computer?.state === "booting";
  const isError = computer?.state === "error";
  const canOpen = Boolean(preview && isRunning);

  return (
    <div>
      <div className="mb-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(48,162,75,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#4ECB71]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#30A24B] shadow-[0_0_6px_rgba(48,162,75,0.8)]" />
              Running
            </span>
          ) : isBooting ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(230,87,7,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#FF8542]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#E65707] animate-pulse" />
              Booting…
            </span>
          ) : isError ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(224,49,49,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#FA5252]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#E03131]" />
              Error
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#1E1E22] px-2.5 py-0.5 text-[12px] font-medium text-[#85858A]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#4E4E54]" />
              Offline
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[#85858A]">
          <button
            type="button"
            onClick={onSettings}
            className="rounded p-1 hover:text-[#ECECEE] transition-colors"
            title="Settings"
          >
            ⚙
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:text-[#ECECEE] transition-colors"
            title="Close panel"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="group relative aspect-[16/10] w-full overflow-hidden rounded-[14px] border border-[#232326] bg-[#0E0E10]">
        {preview && isRunning ? (
          <>
            <iframe
              title="Computer preview"
              src={preview}
              sandbox={screenIframeSandbox(preview)}
              className="pointer-events-none h-full w-full border-0 bg-black"
              allow="clipboard-read; clipboard-write"
              style={{ pointerEvents: previewPointerEvents() }}
            />
            <button
              type="button"
              className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity duration-150 group-hover:opacity-100 cursor-pointer"
              onClick={onOpenFullscreen}
              aria-label="Open computer fullscreen"
            >
              <span className="flex items-center gap-1.5 rounded-lg border border-[#303036] bg-[#161619]/90 px-3 py-1.5 text-[13px] font-medium text-[#ECECEE] shadow-lg backdrop-blur-sm">
                Open screen ↗
              </span>
            </button>
          </>
        ) : isRunning ? (
          <div className="grid h-full w-full place-items-center px-6 text-center">
            <div className="flex flex-col items-center gap-2 text-[#85858A]">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#3A3A40] border-t-[#30A24B]" />
              <span className="text-[13px] font-medium text-[#ECECEE]">Connecting desktop…</span>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="grid h-full w-full place-items-center px-6 text-center cursor-pointer"
            onClick={() => {
              if (isRunning) onOpenFullscreen();
              else onTakeControl();
            }}
          >
            {isBooting ? (
              <div className="flex flex-col items-center gap-2 text-[#A0A0A6]">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#3A3A40] border-t-[#E65707]" />
                <span className="text-[13px] font-medium">Starting desktop…</span>
              </div>
            ) : computer?.busyBotName ? (
              <div className="flex flex-col items-center gap-1 text-[#85858A]">
                <span className="text-[14px] font-medium text-[#ECECEE]">{computer.busyBotName}</span>
                <span className="text-[12px]">is using the computer</span>
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center gap-1 text-[#FA5252]">
                <span className="text-[13.5px] font-medium">Failed to start</span>
                <span className="text-[12px] text-[#85858A]">Click to retry</span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-[#85858A]">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[#4E4E54]">
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                  <line x1="8" y1="21" x2="16" y2="21"></line>
                  <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium text-[#ECECEE]">{label}</span>
                  <span className="text-[11.5px] text-[#6C6C70]">Offline • Click to start</span>
                </div>
              </div>
            )}
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="text-[13px] text-[#85858A]">
          {computer?.busyBotName
            ? `${computer.busyBotName} is using it`
            : computer?.controlHolder === "user"
              ? "You have control"
              : label}
        </span>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Button type="button" variant="ghost" size="sm" onClick={onOpenFullscreen} className="text-[13px] text-[#ECECEE]">
              Open screen
            </Button>
          ) : null}
          {computer?.controlHolder === "user" ? (
            <Button type="button" variant="outline" size="sm" onClick={onRelease}>
              Release
            </Button>
          ) : (
            <Button type="button" variant="outline" size="sm" onClick={onTakeControl}>
              Take control
            </Button>
          )}
        </div>
      </div>
      <MemoryPanel botId={bot.id} onLater={onLater} />
      <RoutinesPanel botId={bot.id} onLater={onLater} />
    </div>
  );
}

function MemoryPanel({ botId, onLater }: { botId: string; onLater: (text: string) => void }) {
  const [documents, setDocuments] = useState<MemoryDocument[]>([]);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [scope, setScope] = useState<"bot" | "user">("bot");
  const [path, setPath] = useState("MEMORY.md");
  const [content, setContent] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setDocuments(await api.memory.list(botId));
  }

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      onLater(err instanceof Error ? err.message : "Could not load memory");
    });
    const poll = window.setInterval(() => void refresh().catch(() => undefined), 10000);
    return () => window.clearInterval(poll);
  }, [botId]);

  async function create() {
    if (!content.trim() || !isMemoryPath(path)) return;
    setBusy(true);
    try {
      await api.memory.create({
        scope,
        botId: scope === "bot" ? botId : undefined,
        path: path.trim(),
        content: content.trim(),
      });
      setContent("");
      setPath("MEMORY.md");
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
        <span className="text-[14px] text-[#85858A]">Memory</span>
        <button type="button" onClick={() => void exportMarkdown()} className="text-[12.5px] text-[#85858A]">
          Export
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {documents.map((document) => (
          <div key={document.id} className="rounded-xl border border-[#202023] bg-[#0D0D0E] px-3 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[14.5px] text-[#ECECEE]">{document.path}</div>
                <div className="mt-0.5 text-[12px] text-[#6C6C70]">
                  {document.scope === "user" ? "shared" : "this bot"} · rev {document.revision}
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
                <div className="line-clamp-3 whitespace-pre-wrap text-[12.5px] text-[#9A9AA0]">
                  {document.content || "Empty"}
                </div>
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
                    Delete
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
          <input
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="MEMORY.md"
            className="h-9 w-full rounded-lg border border-[#202023] bg-[#141416] px-2.5 font-mono text-[13px] text-[#ECECEE] outline-none"
          />
          <textarea
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
              disabled={busy || !content.trim() || !isMemoryPath(path)}
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
          onClick={() => setCreating(true)}
          className="mt-1 flex items-center gap-2.5 px-2.5 py-2.5 text-[14.5px] text-[#7A7A80]"
        >
          + New memory
        </button>
      )}
    </div>
  );
}

function RoutinesPanel({ botId, onLater }: { botId: string; onLater: (text: string) => void }) {
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
      <div className="mt-[30px] mb-3 text-[14px] text-[#85858A]">Routines</div>
      <div className="flex flex-col gap-2">
        {routines.map((routine) => (
          <div key={routine.id} className="rounded-xl border border-[#202023] bg-[#0D0D0E] px-3 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[14.5px] text-[#ECECEE]">{routine.name}</div>
                <div className="mt-0.5 font-mono text-[12px] text-[#6C6C70]">{routine.cron}</div>
                <div className="mt-0.5 text-[12px] text-[#6C6C70]">
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
                  routine.active ? "bg-[#1D3B2A] text-[#8FCB9B]" : "bg-[#1A1A1D] text-[#85858A]"
                }`}
              >
                {routine.active ? "on" : "off"}
              </button>
            </div>
            <div className="mt-2 flex gap-3 text-[12.5px] text-[#85858A]">
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
        <div className="mt-3 rounded-xl border border-[#202023] bg-[#0D0D0E] p-3">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            className="h-9 w-full rounded-lg border border-[#202023] bg-[#141416] px-2.5 text-[13px] text-[#ECECEE] outline-none"
          />
          <input
            value={cron}
            onChange={(event) => setCron(event.target.value)}
            placeholder="0 9 * * *"
            className="mt-2 h-9 w-full rounded-lg border border-[#202023] bg-[#141416] px-2.5 font-mono text-[13px] text-[#ECECEE] outline-none"
          />
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Prompt to send"
            rows={3}
            className="mt-2 w-full resize-none rounded-lg border border-[#202023] bg-[#141416] px-2.5 py-2 text-[13px] text-[#ECECEE] outline-none"
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
          onClick={() => setCreating(true)}
          className="mt-1 flex items-center gap-2.5 px-2.5 py-2.5 text-[14.5px] text-[#7A7A80]"
        >
          + New routine
        </button>
      )}
    </div>
  );
}
