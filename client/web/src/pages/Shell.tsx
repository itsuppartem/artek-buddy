import {
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  type SyntheticEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { abortableDelay, api, classifyError, isLiveTurn, type ShellErrorKind } from "../api";
import {
  type AttentionAlert,
  allowAlert,
  answeredAskBody,
  attentionFingerprint,
  attentionFromBotChange,
  attentionFromEvent,
  isHistoricalEvent,
  parkedAttentionForView,
  rememberShownAlert,
  shouldClearAttentionForView,
  shouldReplaceAttention,
  shouldSendDesktopAlert,
  shouldStickDismissOnView,
  shouldWatchBackgroundBot,
} from "../lib/alerts";
import { composerCanSend } from "../lib/composer";
import {
  composerRedo,
  composerUndo,
  composerUndoKind,
  createComposerHistory,
  pushComposerChange,
  resetComposerHistory,
} from "../lib/composer-undo";
import { fulfillOwnerJob, isAutoOwnerJob, reportOwnerJobError } from "../lib/consent";
import { stripMarkdown } from "../lib/markdown";
import { NEEDS_MODEL_TEXT } from "../lib/models";
import {
  captionForMessage,
  captionTargetId,
  enqueueSend,
  formatOfflineCaption,
  isQueuedMessageId,
  mergeQueuedIntoMessages,
  newQueuedId,
  OFFLINE_CAPTIONS_KEY,
  OFFLINE_QUEUE_KEY,
  type OfflineCaption,
  parseStoredList,
  type QueuedSend,
  rememberCaption,
  removeQueuedSend,
  shouldQueueSend,
  writeStoredList,
} from "../lib/offline-queue";
import {
  embeddableScreenUrl,
  screenFrameLooksFailed,
  shouldFetchScreenUrl,
  shouldRefreshScreenUrl,
  shouldReplaceScreenUrl,
  shouldTakeControl,
} from "../lib/screen";
import { filterBots, inboxEmptyState, type SidebarView, sortInboxBots } from "../lib/sidebar";
import {
  isHiddenLiveDraft,
  isToolNoise,
  mergeThreadSnapshot,
  prependThreadMessagePage,
} from "../lib/thread-events";
import {
  addPendingFiles,
  clipboardFilePaths,
  clipboardShouldClaim,
  droppedFiles,
  filesFromAttachedPayload,
  type PendingFile,
  pasteClipboardData,
  pastedFiles,
  previewKind,
  readClipboardFiles,
  readFileBase64,
  transferFilePaths,
} from "../lib/uploads";
import type {
  Bot,
  ComputerMode,
  ComputerStatus,
  ModelCredentialList,
  ProductEvent,
  ThreadMessage,
  ThreadSnapshot,
} from "../types";
import { BotAvatar } from "../ui/bot-avatar";
import { Button } from "../ui/button";
import {
  IconClose,
  IconComputer,
  IconPlus,
  IconSearch,
  IconSend,
  IconSettings,
  IconStop,
} from "../ui/icons";
import { WindowChrome } from "../ui/window-chrome";
import { BotContextMenu, type ContextMenuPosition } from "./BotContextMenu";
import { MessageContextMenu } from "./MessageContextMenu";
import { applyThreadEvent } from "./shell/apply-thread-event";
import { BotSettings } from "./shell/BotSettings";
import { ComputerOverlay } from "./shell/ComputerOverlay";
import { ComputerPane } from "./shell/ComputerPane";
import { CreateBotForm } from "./shell/CreateBotForm";
import { MessageView, replyExcerpt } from "./shell/MessageView";
import { ModelsPane } from "./shell/ModelsPane";
import { PluginsAsk } from "./shell/PluginsAsk";
import { PluginsPane } from "./shell/PluginsPane";

type Panel = "computer" | "settings" | "create" | "models" | "plugins" | null;

export function ShellPage() {
  const { botId } = useParams();
  const navigate = useNavigate();
  const [bots, setBots] = useState<Bot[]>([]);
  const [botsReady, setBotsReady] = useState(false);
  const [query, setQuery] = useState("");
  const [archivedBots, setArchivedBots] = useState<Bot[]>([]);
  const [sidebarView, setSidebarView] = useState<SidebarView>("inbox");
  const [snapshot, setSnapshot] = useState<ThreadSnapshot | null>(null);
  const [draft, setDraft] = useState("");
  const draftHistory = useRef(createComposerHistory(""));
  const draftChangeAt = useRef(0);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [sending, setSending] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
  const [pluginApps, setPluginApps] = useState<{ slug: string; name: string }[]>([]);
  const [modelState, setModelState] = useState<ModelCredentialList | null>(null);
  const panelAfterSettings = useRef<"computer" | null>(null);
  const panelAfterCreate = useRef<"computer" | null>(null);
  const panelAfterModels = useRef<"computer" | null>(null);
  const creatingBot = useRef(false);
  const filesEpoch = useRef(0);
  const queueFilesRef = useRef<(incoming: File[]) => void>(() => undefined);
  const pendingAlerts = useRef(
    new Map<string, { alert: AttentionAlert; notifyOnFinish: boolean; key: string }>(),
  );
  const fulfilledOwnerJobs = useRef(new Set<string>());
  const [computer, setComputer] = useState<ComputerStatus | null>(null);
  const [screenUrl, setScreenUrl] = useState<string | null>(null);
  const screenUrlRef = useRef<string | null>(null);
  const [screenError, setScreenError] = useState<string | null>(null);
  const [screenEpoch, setScreenEpoch] = useState(0);
  const screenRetries = useRef(0);
  const previewFrameRef = useRef<HTMLIFrameElement>(null);
  const overlayFrameRef = useRef<HTMLIFrameElement>(null);
  const [computerOpen, setComputerOpen] = useState(false);
  const [booting, setBooting] = useState(false);
  const autoBooted = useRef<string | null>(null);
  const sleepHeld = useRef(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<ShellErrorKind>("host");
  const errorKindRef = useRef<ShellErrorKind>("host");
  const [offlineQueue, setOfflineQueue] = useState<QueuedSend[]>(() =>
    parseStoredList<QueuedSend>(window.localStorage.getItem(OFFLINE_QUEUE_KEY)),
  );
  const [offlineCaptions, setOfflineCaptions] = useState<OfflineCaption[]>(() =>
    parseStoredList<OfflineCaption>(window.localStorage.getItem(OFFLINE_CAPTIONS_KEY)),
  );
  const [hostDown, setHostDown] = useState(() => offlineQueue.length > 0);
  const offlineQueueRef = useRef(offlineQueue);
  const offlineCaptionsRef = useRef(offlineCaptions);
  const hostDownRef = useRef(hostDown);
  const flushingQueue = useRef(false);
  offlineQueueRef.current = offlineQueue;
  offlineCaptionsRef.current = offlineCaptions;
  hostDownRef.current = hostDown;
  const [later, setLater] = useState<string | null>(null);
  const [attention, setAttention] = useState<AttentionAlert | null>(null);
  const seenAlertKeys = useRef(new Set<string>());
  const dismissedAlerts = useRef(new Set<string>());
  const stickToLatest = useRef(true);
  const recentKindAt = useRef(new Map<string, number>());
  const prevBotsRef = useRef(new Map<string, Bot>());
  const activeIdRef = useRef<string | undefined>(undefined);
  const botIdRef = useRef<string | undefined>(undefined);
  const botsRef = useRef<Bot[]>([]);
  const shellOpenedAt = useRef(Date.now());
  const freshBotIds = useRef(new Set<string>());
  const previousViewingRef = useRef<string | null>(null);
  const refreshBotsRef = useRef<() => Promise<Bot[]>>(async () => []);
  const considerEventRef = useRef<
    (incoming: ProductEvent, bot: Bot, opts?: { live?: boolean }) => void
  >(() => undefined);
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
  const discardedBotIds = useRef(new Set<string>());
  const heldUnreadIds = useRef(new Set<string>());
  const messageScroll = useRef<HTMLDivElement>(null);

  const active = bots.find((bot) => bot.id === botId);
  activeIdRef.current = active?.id;
  botIdRef.current = botId;
  const thread = active && snapshot?.botId === active.id ? snapshot : null;
  const isParked = thread?.run?.status === "waiting_takeover";
  const isBusy = Boolean(
    (thread?.run && isLiveTurn(thread.run.status)) ||
      (thread && !isParked && (hasLive(thread) || hasActiveWorkers(thread))),
  );

  useEffect(() => {
    botsRef.current = bots;
  }, [bots]);

  useEffect(() => {
    filesEpoch.current += 1;
    setPendingFiles([]);
  }, [botId]);

  function patchBotUnread(id: string, unread: boolean) {
    setBots((list) => list.map((bot) => (bot.id === id ? { ...bot, unread } : bot)));
    const stored = prevBotsRef.current.get(id);
    if (stored) prevBotsRef.current.set(id, { ...stored, unread });
    botsRef.current = botsRef.current.map((bot) => (bot.id === id ? { ...bot, unread } : bot));
  }

  function markOpenThreadRead(id: string) {
    heldUnreadIds.current.delete(id);
    patchBotUnread(id, false);
    void api.threads.markRead(id).catch(() => undefined);
  }

  useEffect(() => {
    if (!botId) return;
    markOpenThreadRead(botId);
  }, [botId]);

  function dispatchAlert(next: AttentionAlert, key: string, notifyOnFinish: boolean) {
    if (!allowAlert(next, notifyOnFinish)) return;
    if (seenAlertKeys.current.has(key)) return;
    if (dismissedAlerts.current.has(attentionFingerprint(next))) {
      seenAlertKeys.current.add(key);
      return;
    }
    const kindKey = `${next.botId}:${next.kind}`;
    const now = Date.now();
    const viewing = activeIdRef.current || botIdRef.current || null;
    if (
      !shouldSendDesktopAlert({
        windowFocused: true,
        viewingBotId: viewing,
        alertBotId: next.botId,
      })
    ) {
      const held = pendingAlerts.current.get(next.botId);
      if (!held || shouldReplaceAttention(held.alert, next)) {
        pendingAlerts.current.set(next.botId, { alert: next, notifyOnFinish, key });
      }
      return;
    }
    if (
      rememberShownAlert(seenAlertKeys.current, recentKindAt.current, key, kindKey, now) === "skip"
    ) {
      return;
    }
    if (seenAlertKeys.current.size > 250) {
      const oldest = seenAlertKeys.current.values().next().value;
      if (oldest) seenAlertKeys.current.delete(oldest);
    }
    pendingAlerts.current.delete(next.botId);
    setAttention((current) => (shouldReplaceAttention(current, next) ? next : current));
  }

  function flushHeldAlerts() {
    const viewing = activeIdRef.current || botIdRef.current || null;
    for (const [id, held] of [...pendingAlerts.current.entries()]) {
      if (id === viewing) continue;
      pendingAlerts.current.delete(id);
      dispatchAlert(held.alert, held.key, held.notifyOnFinish);
    }
  }

  function raiseParkedAlerts() {
    flushHeldAlerts();
    const viewing = activeIdRef.current || botIdRef.current || null;
    const next = parkedAttentionForView(
      botsRef.current.map((bot) => ({
        id: bot.id,
        name: bot.name,
        status: bot.status,
        unread: bot.unread,
        preview: bot.preview,
        updatedAt: bot.updatedAt,
      })),
      viewing,
      dismissedAlerts.current,
      shellOpenedAt.current,
      freshBotIds.current,
    );
    if (!next) return;
    const source = botsRef.current.find((bot) => bot.id === next.botId);
    dispatchAlert(next, `${next.botId}:${next.kind}:parked`, source?.notifyOnFinish ?? true);
  }

  function openBot(id: string) {
    activeIdRef.current = id;
    botIdRef.current = id;
    navigate(`/app/${id}`);
  }

  function dismissAttention(alert: AttentionAlert | null = attention) {
    if (alert) {
      dismissedAlerts.current.add(attentionFingerprint(alert));
      pendingAlerts.current.delete(alert.botId);
    }
    setAttention(null);
  }

  function startOwnerFulfill(consentId: string) {
    if (!consentId || fulfilledOwnerJobs.current.has(consentId)) return;
    fulfilledOwnerJobs.current.add(consentId);
    void fulfillOwnerJob(consentId).catch((err) => {
      fulfilledOwnerJobs.current.delete(consentId);
      void reportOwnerJobError(consentId, err);
    });
  }

  function considerEvent(incoming: ProductEvent, bot: Bot, opts?: { live?: boolean }) {
    const granted = isAutoOwnerJob(incoming);
    if (granted) startOwnerFulfill(granted.consentId);
    if (!opts?.live && isHistoricalEvent(incoming, shellOpenedAt.current)) return;
    const next = attentionFromEvent(incoming, bot.name);
    const answered = answeredAskBody(incoming);
    if (answered) {
      dismissedAlerts.current.add(`${bot.id}:ask:${answered}`);
      pendingAlerts.current.delete(bot.id);
    }
    flushHeldAlerts();
    if (next) dispatchAlert(next, incoming.id, bot.notifyOnFinish);
    if (incoming.type === "run.started") {
      const running = { ...bot, status: "running" };
      botsRef.current = botsRef.current.map((item) => (item.id === bot.id ? running : item));
      const stored = prevBotsRef.current.get(bot.id);
      if (stored) prevBotsRef.current.set(bot.id, { ...stored, status: "running" });
      setBots((list) =>
        list.map((item) => (item.id === bot.id ? { ...item, status: "running" } : item)),
      );
    }
    if (incoming.type === "computer.takeover.requested") {
      const parked = {
        ...bot,
        status: "waiting_takeover",
        updatedAt: new Date().toISOString(),
      };
      botsRef.current = botsRef.current.map((item) => (item.id === bot.id ? parked : item));
      const stored = prevBotsRef.current.get(bot.id);
      if (stored) prevBotsRef.current.set(bot.id, { ...stored, status: "waiting_takeover" });
      setBots((list) =>
        list.map((item) => (item.id === bot.id ? { ...item, status: "waiting_takeover" } : item)),
      );
      raiseParkedAlerts();
      void refreshBotsRef.current().catch(() => undefined);
    }
    if (incoming.type === "run.completed" || incoming.type === "run.failed") {
      void refreshBotsRef.current().catch(() => undefined);
    }
  }
  considerEventRef.current = considerEvent;

  useEffect(() => {
    raiseParkedAlerts();
    void refreshBotsRef.current().catch(() => undefined);
  }, [active?.id]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const viewing = activeIdRef.current || botIdRef.current;
      const watch = botsRef.current.some((bot) =>
        shouldWatchBackgroundBot(bot.status, bot.id, viewing),
      );
      if (watch) {
        const needsList = botsRef.current.some(
          (bot) =>
            bot.id !== viewing &&
            (bot.status === "queued" || bot.status === "leased" || bot.status === "running"),
        );
        if (needsList) void refreshBotsRef.current().catch(() => undefined);
        else raiseParkedAlerts();
      }
    }, 2_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const viewing = activeIdRef.current || botIdRef.current || null;
    if (shouldClearAttentionForView(attention, viewing)) {
      if (shouldStickDismissOnView(attention, viewing, previousViewingRef.current)) {
        dismissedAlerts.current.add(attentionFingerprint(attention));
      }
      setAttention(null);
    }
    previousViewingRef.current = viewing;
  }, [active?.id, attention]);

  async function refreshBots() {
    const list = await api.bots.list();
    const prev = prevBotsRef.current;
    if (prev.size) {
      for (const next of list) {
        const before = prev.get(next.id);
        if (!before) continue;
        const alert = attentionFromBotChange(before, next);
        if (alert) {
          const updated = Date.parse(next.updatedAt);
          if (
            !freshBotIds.current.has(next.id) &&
            Number.isFinite(updated) &&
            updated < shellOpenedAt.current
          ) {
            continue;
          }
          dispatchAlert(alert, `${next.id}:${alert.kind}:${next.updatedAt}`, next.notifyOnFinish);
        }
      }
    }
    const viewing = activeIdRef.current || botIdRef.current;
    if (viewing && !heldUnreadIds.current.has(viewing)) {
      const open = list.find((item) => item.id === viewing);
      if (open?.unread) {
        open.unread = false;
        void api.threads.markRead(viewing).catch(() => undefined);
      }
    }
    prevBotsRef.current = new Map(list.map((item) => [item.id, item]));
    botsRef.current = list;
    for (const item of list) discardedBotIds.current.delete(item.id);
    const archivedList = await api.bots.listArchived().catch(() => [] as Bot[]);
    setBots(list);
    raiseParkedAlerts();
    setArchivedBots(archivedList);
    if (archivedList.length === 0) setSidebarView("inbox");
    setBotsReady(true);
    void refreshModels();
    return list;
  }
  refreshBotsRef.current = refreshBots;

  async function refreshModels() {
    try {
      setModelState(await api.models.credentials());
    } catch {
      // Host errors stay on the existing banner.
    }
  }

  function openModels() {
    panelAfterModels.current = panel === "computer" ? "computer" : null;
    setPanel("models");
  }

  function closeModels() {
    setPanel(panelAfterModels.current);
    panelAfterModels.current = null;
  }

  function openPlugins() {
    setPanel("plugins");
  }

  async function refreshPlugins() {
    try {
      const status = await api.connections.status();
      if (!status.configured) {
        setPluginApps([]);
        return;
      }
      const listed = await api.connections.list();
      setPluginApps(
        (listed.connections ?? [])
          .filter((row) => row.status === "connected")
          .map((row) => ({ slug: row.provider, name: row.displayName })),
      );
    } catch {
      setPluginApps([]);
    }
  }

  useEffect(() => {
    void refreshPlugins();
  }, []);

  function persistQueue(next: QueuedSend[]): QueuedSend[] {
    try {
      writeStoredList(window.localStorage, OFFLINE_QUEUE_KEY, next);
    } catch {
      // Memory still holds the queue if storage is full.
    }
    return next;
  }

  function persistCaptions(next: OfflineCaption[]): OfflineCaption[] {
    try {
      writeStoredList(window.localStorage, OFFLINE_CAPTIONS_KEY, next);
    } catch {
      // Caption is optional after a reload.
    }
    return next;
  }

  function showError(err: unknown, fallback: string) {
    const classified = classifyError(err);
    const message = classified.message || fallback;
    errorKindRef.current = classified.kind;
    setErrorKind(classified.kind);
    if (classified.kind === "host") {
      setHostDown(true);
      return;
    }
    setError(message);
  }

  const reconnecting = useRef(false);

  async function reconnectHost(loadBots = false) {
    if (reconnecting.current) return;
    reconnecting.current = true;
    try {
      await api.health();
      setHostDown(false);
      await flushOfflineQueue();
      const recovering = errorKindRef.current === "host";
      if (loadBots || recovering) {
        await refreshBotsRef.current();
      }
      if (loadBots || recovering) {
        setError(null);
      }
    } catch (err) {
      setBotsReady(true);
      showError(err, "Could not reach the host");
    } finally {
      reconnecting.current = false;
    }
  }

  function parkSend(
    botId: string,
    text: string,
    replyToId: string | null,
    attachments: QueuedSend["attachments"],
  ) {
    const item: QueuedSend = {
      id: newQueuedId(),
      botId,
      text,
      replyToId,
      attachments,
      queuedAt: Date.now(),
    };
    setOfflineQueue((queue) => persistQueue(enqueueSend(queue, item)));
    setHostDown(true);
    setReplyTo(null);
  }

  async function flushOfflineQueue() {
    if (flushingQueue.current) return;
    const items = offlineQueueRef.current;
    if (!items.length) return;
    flushingQueue.current = true;
    try {
      for (const item of items) {
        try {
          await api.threads.send(item.botId, item.text, item.replyToId, item.attachments);
          const snap =
            activeIdRef.current === item.botId
              ? await refreshThread(item.botId)
              : await api.threads.get(item.botId).catch(() => null);
          const messages = snap?.messages ?? [];
          setOfflineCaptions((captions) => {
            const taken = new Set(captions.map((caption) => caption.messageId));
            const messageId = captionTargetId(item, messages, taken);
            if (!messageId) return captions;
            return persistCaptions(
              rememberCaption(captions, {
                messageId,
                botId: item.botId,
                queuedAt: item.queuedAt,
              }),
            );
          });
          setOfflineQueue((queue) => persistQueue(removeQueuedSend(queue, item.id)));
        } catch (err) {
          const classified = classifyError(err);
          if (classified.kind === "host") {
            setHostDown(true);
            return;
          }
          if (classified.kind === "auth") {
            showError(err, classified.message);
            return;
          }
          showError(err, "Send failed");
          setOfflineQueue((queue) => persistQueue(removeQueuedSend(queue, item.id)));
          return;
        }
      }
    } finally {
      flushingQueue.current = false;
    }
  }

  async function forgetDevice() {
    try {
      await api.local.unpair();
    } catch {
      // Reload anyway so the pairing screen can appear if the token is gone.
    }
    window.location.assign("/");
  }

  function adoptScreenUrl(next: string | null) {
    const current = screenUrlRef.current;
    if (!shouldReplaceScreenUrl(current, next)) return;
    screenUrlRef.current = next;
    setScreenUrl(next);
  }

  function onScreenFrameLoad(event: SyntheticEvent<HTMLIFrameElement>) {
    if (screenFrameLooksFailed(event.currentTarget)) {
      setScreenError("Desktop is starting…");
      return;
    }
    screenRetries.current = 0;
    setScreenError(null);
  }

  function reloadScreenFrames() {
    for (const frame of [previewFrameRef.current, overlayFrameRef.current]) {
      if (!frame) continue;
      const src = frame.getAttribute("src");
      if (src) frame.src = src;
    }
  }

  function retryScreen() {
    if (!active) return;
    setScreenEpoch((value) => value + 1);
    void ensureScreenUrl(active.id, true, true);
  }

  async function ensureScreenUrl(id: string, available: boolean, force = false) {
    if (!available) {
      adoptScreenUrl(null);
      setScreenError(null);
      return;
    }
    if (!force && !shouldRefreshScreenUrl(screenUrlRef.current)) return;
    try {
      const screen = await api.computer.screenUrl(id);
      adoptScreenUrl(embeddableScreenUrl(screen.url));
      setScreenError(null);
    } catch (err) {
      setScreenError(err instanceof Error ? err.message : "Could not open the screen");
    }
  }

  function forgetBot(id: string, wasActive: boolean) {
    discardedBotIds.current.add(id);
    if (wasActive) {
      activeIdRef.current = undefined;
      setSnapshot(null);
      setComputer(null);
      screenUrlRef.current = null;
      setScreenUrl(null);
      setScreenError(null);
      writeDraft("", true);
      setPendingFiles([]);
      setReplyTo(null);
    }
    setBots((list) => list.filter((item) => item.id !== id));
  }

  async function restoreBot(bot: Bot) {
    try {
      await api.bots.restore(bot.id);
      discardedBotIds.current.delete(bot.id);
      setSidebarView("inbox");
      await refreshBots();
      navigate(`/app/${bot.id}`);
    } catch (err) {
      showError(err, "Could not restore chat");
    }
  }

  async function refreshThread(id: string) {
    if (discardedBotIds.current.has(id) || activeIdRef.current !== id) return null;
    const scrollElement = messageScroll.current;
    const stickToEnd =
      !scrollElement ||
      scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight < 80;
    const snap = await api.threads.get(id);
    if (discardedBotIds.current.has(id) || activeIdRef.current !== id) return snap;
    setSnapshot((prev) =>
      mergeThreadSnapshot(prev, snap, expandedHistoryThread.current === snap.threadId),
    );
    setComputer(snap.computer);
    if (snap.pendingAutoConsentId) startOwnerFulfill(snap.pendingAutoConsentId);
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
    const requested = active.id;
    setLoadingOlder(true);
    try {
      const page = await api.threads.messages(requested, snapshot.olderCursor);
      if (activeIdRef.current !== requested) return;
      expandedHistoryThread.current = page.threadId;
      setSnapshot((prev) => prependThreadMessagePage(prev, page));
      window.requestAnimationFrame(() => {
        const element = messageScroll.current;
        if (element) element.scrollTop += element.scrollHeight - previousHeight;
      });
    } catch (err) {
      if (activeIdRef.current === requested) showError(err, "Could not load earlier messages");
    } finally {
      setLoadingOlder(false);
    }
  }

  useEffect(() => {
    void reconnectHost(true);
    const poll = window.setInterval(() => void reconnectHost(false), 4000);
    return () => window.clearInterval(poll);
  }, []);

  useEffect(() => {
    if (!botsReady) return;
    if (botId && bots.some((bot) => bot.id === botId)) return;
    const fallback = sortInboxBots(bots)[0];
    if (!botId && fallback) {
      navigate(`/app/${fallback.id}`, { replace: true });
      return;
    }
    if (botId && !bots.some((bot) => bot.id === botId)) {
      navigate(fallback ? `/app/${fallback.id}` : "/app", { replace: true });
    }
  }, [botsReady, botId, bots, navigate]);

  useEffect(() => {
    if (!active) {
      if (botId) return;
      sleepHeld.current = false;
      setSnapshot(null);
      setComputer(null);
      screenUrlRef.current = null;
      setScreenUrl(null);
      setScreenError(null);
      return;
    }
    sleepHeld.current = false;
    screenUrlRef.current = null;
    setScreenUrl(null);
    setScreenError(null);
    setScreenEpoch(0);
    screenRetries.current = 0;
    setSnapshot((prev) => (prev?.botId === active.id ? prev : null));
    setComputer(null);
    expandedHistoryThread.current = null;
    const abort = new AbortController();
    void (async () => {
      const _snap = await refreshThread(active.id).catch((err: unknown) => {
        showError(err, "Could not load thread");
        return null;
      });
      if (abort.signal.aborted) return;
      let after: string | null = null;
      let retryMs = 250;
      while (!abort.signal.aborted) {
        try {
          for await (const event of api.threads.subscribe(active.id, after, abort.signal)) {
            if (abort.signal.aborted) break;
            if (event.type === "thread.replay.gap") {
              after = null;
              retryMs = 250;
              void refreshThread(active.id).catch(() => undefined);
              void ensureScreenUrl(active.id, true, true);
              continue;
            }
            after = event.id;
            retryMs = 250;
            const leftChat =
              discardedBotIds.current.has(active.id) ||
              abort.signal.aborted ||
              activeIdRef.current !== active.id;
            if (!leftChat) {
              applyThreadEvent(event, setSnapshot, setComputer);
            }
            const bot = botsRef.current.find((item) => item.id === active.id) ?? active;
            considerEvent(event, bot);
            if (leftChat) break;
            if (event.type === "run.completed" || event.type === "run.failed") {
              void refreshBotsRef.current().catch(() => undefined);
              void refreshThread(active.id).catch(() => undefined);
            }
          }
        } catch (err) {
          if (abort.signal.aborted) break;
          const classified = classifyError(err);
          if (classified.kind === "auth") {
            showError(err, classified.message);
            break;
          }
          if (classified.kind === "host") setHostDown(true);
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
    stickToLatest.current = true;
  }, [active?.id]);

  useLayoutEffect(() => {
    if (!stickToLatest.current) return;
    const element = messageScroll.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [thread?.messages, thread?.run?.status, active?.id]);

  useEffect(() => {
    const abort = new AbortController();
    void (async () => {
      let retryMs = 250;
      while (!abort.signal.aborted) {
        try {
          for await (const event of api.events.subscribe(abort.signal)) {
            if (abort.signal.aborted) break;
            retryMs = 250;
            const bot = botsRef.current.find((item) => item.id === event.botId);
            if (bot) considerEventRef.current(event, bot, { live: true });
          }
        } catch (err) {
          if (abort.signal.aborted) break;
          if (classifyError(err).kind === "auth") break;
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
    return () => abort.abort();
  }, []);

  useEffect(() => {
    setReplyTo(null);
    setMessageMenu(null);
  }, [active?.id]);

  useEffect(() => {
    if (panel !== "computer") autoBooted.current = null;
  }, [panel]);

  useEffect(() => {
    setComputerOpen(false);
  }, [active?.id]);

  useEffect(() => {
    if ((panel !== "settings" && panel !== "computer") || !active) return;
    void api.computer
      .status(active.id)
      .then(setComputer)
      .catch(() => undefined);
  }, [panel, active?.id]);

  const runLive = snapshot?.run?.status === "running" || snapshot?.run?.status === "waiting_input";

  useEffect(() => {
    if ((panel !== "computer" && !computerOpen) || !active) return;
    if (computer?.state !== "running" && !runLive) return;
    const ping = () =>
      void api.computer
        .status(active.id)
        .then(setComputer)
        .catch(() => undefined);
    ping();
    const ms = computer?.controlHolder === "user" ? 15_000 : 60_000;
    const timer = window.setInterval(ping, ms);
    return () => window.clearInterval(timer);
  }, [panel, computerOpen, active?.id, computer?.state, computer?.controlHolder, runLive]);

  useEffect(() => {
    if (!active) return;
    if (!shouldFetchScreenUrl(panel === "computer", computerOpen, computer?.state)) return;
    void ensureScreenUrl(active.id, true);
  }, [panel, computerOpen, active?.id, computer?.state]);

  useEffect(() => {
    if (!active || computer?.state !== "running" || !screenError) return;
    screenRetries.current = 0;
    const timer = window.setInterval(() => {
      if (screenRetries.current >= 4) {
        window.clearInterval(timer);
        return;
      }
      screenRetries.current += 1;
      reloadScreenFrames();
      void ensureScreenUrl(active.id, true, true);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [active?.id, computer?.state, screenError]);

  useEffect(() => {
    if (!computerOpen) return;
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setComputerOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [computerOpen]);

  const filtered = useMemo(
    () => filterBots(sortInboxBots(bots), query, (bot) => stripMarkdown(bot.preview || bot.title)),
    [bots, query],
  );
  const filteredArchived = useMemo(
    () => filterBots(archivedBots, query, (bot) => stripMarkdown(bot.preview || bot.title)),
    [archivedBots, query],
  );
  const emptyInbox = inboxEmptyState(bots.length, archivedBots.length);
  const needsModel = !modelState?.defaultModel;

  function writeDraft(value: string, reset = false) {
    if (reset) {
      draftHistory.current = resetComposerHistory(value);
      draftChangeAt.current = 0;
    } else {
      const now = Date.now();
      draftHistory.current = pushComposerChange(
        draftHistory.current,
        value,
        now,
        draftChangeAt.current,
      );
      draftChangeAt.current = now;
    }
    setDraft(value);
    window.requestAnimationFrame(() => sizeComposer());
  }

  function sizeComposer() {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const kind = composerUndoKind(event);
    if (kind === "undo") {
      event.preventDefault();
      const next = composerUndo(draftHistory.current);
      if (next) {
        draftHistory.current = next.history;
        setDraft(next.value);
        window.requestAnimationFrame(() => sizeComposer());
      }
      return;
    }
    if (kind === "redo") {
      event.preventDefault();
      const next = composerRedo(draftHistory.current);
      if (next) {
        draftHistory.current = next.history;
        setDraft(next.value);
        window.requestAnimationFrame(() => sizeComposer());
      }
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const typed = event.currentTarget.value;
      if (composerRef.current) composerRef.current.value = typed;
      void send();
    }
  }

  function queueFiles(incoming: File[]) {
    if (!active || !incoming.length) return;
    const { files, error: attachError } = addPendingFiles(pendingFiles, incoming);
    if (attachError) {
      errorKindRef.current = "action";
      setErrorKind("action");
      setError(attachError);
      return;
    }
    setPendingFiles(files);
  }
  queueFilesRef.current = queueFiles;

  useEffect(() => {
    const win = window as Window & {
      __artekAttachPastedImage?: (contentBase64: string, type: string, name: string) => void;
    };
    win.__artekAttachPastedImage = (contentBase64, type, name) => {
      queueFilesRef.current(filesFromAttachedPayload([{ name, type, contentBase64 }]));
    };
    return () => {
      delete win.__artekAttachPastedImage;
    };
  }, []);

  function attachLocalPaths(paths: string[]) {
    if (!active || !paths.length) return;
    const epoch = filesEpoch.current;
    void api.local
      .attachFiles(paths)
      .then((payload) => {
        if (epoch !== filesEpoch.current) return;
        queueFiles(filesFromAttachedPayload(payload.files));
      })
      .catch((err: unknown) => {
        if (epoch !== filesEpoch.current) return;
        const classified = classifyError(err);
        errorKindRef.current = classified.kind;
        setErrorKind(classified.kind);
        setError(classified.message);
      });
  }

  function onChatPaste(event: ClipboardEvent<HTMLElement>) {
    const wrapped = { clipboardData: pasteClipboardData(event) };
    if (!clipboardShouldClaim(wrapped)) return;
    event.preventDefault();
    event.stopPropagation();
    const files = pastedFiles(wrapped);
    if (files.length) {
      queueFiles(files);
      return;
    }
    const paths = clipboardFilePaths(wrapped);
    if (paths.length) {
      attachLocalPaths(paths);
      return;
    }
    const epoch = filesEpoch.current;
    void readClipboardFiles(wrapped).then((extra) => {
      if (epoch !== filesEpoch.current) return;
      if (extra.length) queueFiles(extra);
    });
  }

  function onComposerDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    const files = droppedFiles(event);
    if (files.length) {
      queueFiles(files);
      return;
    }
    attachLocalPaths(transferFilePaths(event.dataTransfer));
  }

  async function send(textOverride?: string) {
    const text = (textOverride ?? composerRef.current?.value ?? draft).trim();
    const files = textOverride == null ? pendingFiles : [];
    if (!active) {
      if (text || files.length) showError(new Error("No chat is open"), "Send failed");
      return;
    }
    if (sending || (!text && !files.length)) return;
    const replyId = replyTo?.id ?? null;
    const targetId = active.id;
    if (textOverride == null) {
      filesEpoch.current += 1;
      writeDraft("", true);
      setPendingFiles([]);
    }
    setError(null);
    setSending(true);
    let attachments: QueuedSend["attachments"];
    try {
      attachments = files.length
        ? await Promise.all(
            files.map(async (item) => ({
              name: item.file.name,
              contentBase64: await readFileBase64(item.file),
              mimeType: item.file.type || undefined,
            })),
          )
        : undefined;
      if (hostDownRef.current) {
        parkSend(targetId, text, replyId, attachments);
        return;
      }
      await api.threads.send(targetId, text, replyId, attachments);
      setReplyTo(null);
    } catch (err) {
      const classified = classifyError(err);
      if (shouldQueueSend(classified.kind)) {
        parkSend(targetId, text, replyId, attachments);
        return;
      }
      if (textOverride == null) {
        writeDraft(text);
        setPendingFiles(files);
      }
      showError(err, "Send failed");
      return;
    } finally {
      setSending(false);
    }
    void refreshThread(targetId).catch(() => undefined);
  }

  async function stop() {
    if (!active) return;
    try {
      await api.threads.stop(active.id);
      await refreshThread(active.id);
    } catch (err) {
      showError(err, "Stop failed");
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
  }): Promise<boolean> {
    if (!active) return false;
    sleepHeld.current = false;
    const needsBoot = force || computer?.state !== "running" || !screenUrlRef.current;
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
      await ensureScreenUrl(active.id, true, takeControl || !screenUrlRef.current);
      return true;
    } catch (err) {
      setLater(err instanceof Error ? err.message : "Could not boot the computer");
      return false;
    } finally {
      setBooting(false);
    }
  }

  function clearScreen() {
    screenUrlRef.current = null;
    setScreenUrl(null);
    setScreenError(null);
    setScreenEpoch((value) => value + 1);
  }

  async function restartComputer() {
    if (!active) return;
    sleepHeld.current = false;
    autoBooted.current = active.id;
    try {
      const status = await api.computer.restart(active.id);
      setComputer(status);
      await ensureScreenUrl(active.id, true, true);
    } catch (err) {
      setLater(err instanceof Error ? err.message : "Could not restart the computer");
    }
  }

  async function stopComputer() {
    if (!active) return;
    try {
      const status = await api.computer.stop(active.id);
      setComputer(status);
      sleepHeld.current = true;
      autoBooted.current = active.id;
      clearScreen();
    } catch (err) {
      setLater(err instanceof Error ? err.message : "Could not stop the computer");
    }
  }

  async function resetComputer() {
    if (!active) return;
    try {
      const status = await api.computer.reset(active.id);
      setComputer(status);
      sleepHeld.current = true;
      autoBooted.current = active.id;
      clearScreen();
    } catch (err) {
      setLater(err instanceof Error ? err.message : "Could not reset the computer");
    }
  }

  async function openOverlay(source: "preview" | "button") {
    if (!active) return;
    const ok = await bootComputer({
      takeControl: shouldTakeControl(source),
      overlay: computer?.state !== "running",
      force: computer?.state !== "running",
    });
    if (ok) setComputerOpen(true);
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
    const name = input.name.trim();
    if (!name || creatingBot.current) return;
    creatingBot.current = true;
    try {
      const bot = await api.bots.create({
        name,
        title: input.title,
        description: input.description,
        instructions: input.description,
        computerMode: input.computerMode,
      });
      freshBotIds.current.add(bot.id);
      await refreshBots();
      navigate(`/app/${bot.id}`);
      setPanel(panelAfterCreate.current);
      panelAfterCreate.current = null;
    } catch (err) {
      showError(err, "Could not create chat");
    } finally {
      creatingBot.current = false;
    }
  }

  function openCreate() {
    panelAfterCreate.current = panel === "computer" ? "computer" : null;
    setPanel("create");
  }

  async function deleteBot(bot: Bot, deleteMemories: boolean = false) {
    try {
      await api.bots.remove(bot.id, deleteMemories);
      forgetBot(bot.id, active?.id === bot.id);
      setPanel(null);
      await refreshBots();
    } catch (err) {
      showError(err, "Could not delete chat");
    }
  }

  useEffect(() => {
    if (!later) return;
    const timer = window.setTimeout(() => setLater(null), 2400);
    return () => window.clearTimeout(timer);
  }, [later]);

  return (
    <div className="relative flex h-full min-w-0 overflow-hidden bg-ink text-paper">
      <aside className="flex w-[252px] shrink-0 flex-col border-r border-hairline bg-[#1a1613]">
        <div className="app-drag flex items-center justify-between px-3 pb-2 pt-3">
          <WindowChrome />
        </div>
        <div className="mb-2 flex items-center gap-2 px-3">
          <label className="flex min-w-0 flex-1 items-center gap-2 rounded-[8px] border border-hairline bg-raised px-2.5 py-1.5 text-[14px] text-mute">
            <IconSearch />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search"
              aria-label="Search inbox"
              className="w-full bg-transparent"
            />
          </label>
          <button
            type="button"
            onClick={() => openCreate()}
            className="app-no-drag inline-flex h-[34px] shrink-0 items-center gap-1 rounded-[8px] border border-hairline bg-raised px-2.5 text-[13px] text-paper"
          >
            <IconPlus />
            New bot
          </button>
        </div>
        <div className="ab-scroll flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 pb-2.5">
          {sidebarView === "archived" ? (
            <>
              <button
                type="button"
                data-testid="back-inbox"
                onClick={() => setSidebarView("inbox")}
                className="mb-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13.5px] text-mute hover:bg-raised hover:text-paper"
              >
                ← Inbox
              </button>
              <div data-testid="archived-list" className="flex flex-col gap-0.5">
                {filteredArchived.map((bot) => (
                  <div
                    key={bot.id}
                    data-testid="archived-bot-row"
                    data-bot-id={bot.id}
                    className="flex items-center gap-3 rounded-xl px-2.5 py-[11px]"
                  >
                    <BotAvatar color={bot.color} size={38} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-display text-[14.5px] text-paper">
                        {bot.name}
                      </div>
                      <div className="mt-0.5 truncate text-[12.5px] text-mute">
                        {stripMarkdown(bot.preview || bot.title)}
                      </div>
                    </div>
                    <button
                      type="button"
                      data-testid="restore-chat"
                      onClick={() => void restoreBot(bot)}
                      className="shrink-0 rounded-lg border border-hairline px-2.5 py-1 text-[12.5px] text-paper hover:bg-raised"
                    >
                      Restore
                    </button>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              {filtered.map((bot) => (
                <button
                  key={bot.id}
                  type="button"
                  data-testid="bot-row"
                  data-bot-id={bot.id}
                  data-bot-name={bot.name}
                  aria-label={`Open chat ${bot.name}`}
                  onClick={() => openBot(bot.id)}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    setContextMenu({
                      bot,
                      position: { x: event.clientX, y: event.clientY },
                    });
                  }}
                  className={`flex gap-2.5 border-l-[3px] px-2.5 py-[11px] text-left ${
                    active?.id === bot.id
                      ? "border-tan bg-plate"
                      : "border-transparent hover:bg-raised"
                  }`}
                >
                  <BotAvatar color={bot.color} size={38} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className={`flex items-center gap-1.5 font-display text-[14.5px] text-paper ${
                          bot.unread ? "font-semibold" : "font-normal"
                        }`}
                      >
                        {bot.name}
                        {bot.pinned ? (
                          <span title="Pinned" className="text-[11px] text-mute">
                            📌
                          </span>
                        ) : null}
                      </span>
                      <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] text-mute">
                        {bot.status === "idle" ? "" : bot.status}
                        {bot.unread ? (
                          <span
                            data-testid="unread-dot"
                            aria-hidden="true"
                            className="inline-block h-[7px] w-[7px] bg-tan"
                          />
                        ) : null}
                      </span>
                    </div>
                    <div
                      data-testid="bot-preview"
                      className={`mt-0.5 truncate text-[12.5px] ${
                        bot.unread ? "font-medium text-paper" : "text-mute"
                      }`}
                    >
                      {stripMarkdown(bot.preview || bot.title)}
                    </div>
                  </div>
                </button>
              ))}
              {archivedBots.length > 0 ? (
                <button
                  type="button"
                  data-testid="open-archived"
                  onClick={() => setSidebarView("archived")}
                  className="mt-1 flex items-center justify-between rounded-xl px-2.5 py-[11px] text-left text-[14px] text-mute hover:bg-raised hover:text-paper"
                >
                  <span>Archived</span>
                  <span data-testid="archived-count">{archivedBots.length}</span>
                </button>
              ) : null}
            </>
          )}
        </div>
        <button
          type="button"
          data-testid="open-plugins"
          aria-label="Plugins"
          onClick={() => openPlugins()}
          className={`flex w-full items-center gap-[11px] border-t px-[14px] py-3.5 text-left ${
            panel === "plugins" ? "border-tan bg-plate" : "border-hairline hover:bg-raised"
          }`}
        >
          <span className="grid h-8 w-8 place-items-center rounded-full bg-raised text-[12px] text-mute">
            P
          </span>
          <span className="min-w-0">
            <span className="block text-[14px] text-paper">Plugins</span>
          </span>
        </button>
        <button
          type="button"
          data-testid="open-models"
          data-models-ready={needsModel ? "false" : "true"}
          aria-label="Models"
          onClick={() => openModels()}
          className={`flex w-full items-center gap-[11px] border-t px-[14px] py-3.5 text-left ${
            panel === "models" ? "border-tan bg-plate" : "border-hairline hover:bg-raised"
          }`}
        >
          <span className="grid h-8 w-8 place-items-center rounded-full bg-raised text-[12px] text-mute">
            Y
          </span>
          <span className="min-w-0">
            <span className="block text-[13px] text-mute">You</span>
            <span className="block text-[14px] text-paper">Models</span>
          </span>
        </button>
      </aside>

      <main
        data-testid="thread-pane"
        className="relative flex min-w-0 flex-1 flex-col bg-ink"
        onPaste={onChatPaste}
      >
        <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
          <div data-testid="thread-header" className="flex min-w-0 items-center gap-3">
            {active ? <BotAvatar color={active.color} size={26} /> : null}
            <span className="min-w-0 truncate font-display text-[16px] font-semibold text-paper">
              {active?.name ?? "Select a bot"}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              disabled={!active}
              onClick={() => setPanel((current) => (current === "computer" ? null : "computer"))}
              className={`inline-flex h-[34px] items-center gap-1.5 rounded-[8px] border px-2.5 text-[13px] disabled:opacity-40 ${
                panel === "computer"
                  ? "border-tan bg-raised text-paper"
                  : "border-hairline bg-raised text-paper"
              }`}
            >
              <IconComputer />
              Computer
            </button>
            <button
              type="button"
              disabled={!active}
              onClick={() => {
                panelAfterSettings.current = panel === "computer" ? "computer" : null;
                setPanel("settings");
              }}
              className={`inline-flex h-[34px] items-center gap-1.5 rounded-[8px] border px-2.5 text-[13px] disabled:opacity-40 ${
                panel === "settings"
                  ? "border-tan bg-raised text-paper"
                  : "border-hairline bg-raised text-paper"
              }`}
            >
              <IconSettings />
              Settings
            </button>
          </div>
        </div>
        {hostDown ? (
          <div className="flex w-full shrink-0 flex-col gap-2 px-4 py-2">
            <div
              data-testid="reconnect-banner"
              className="flex w-full items-center gap-2 border border-hairline border-l-[3px] border-l-tan bg-plate px-3 py-2 text-[13.5px] text-paper"
            >
              <p className="min-w-0 flex-1 text-left">Reconnecting to the host</p>
              <button
                type="button"
                onClick={() => void reconnectHost(true)}
                className="shrink-0 px-2 text-[13px] font-medium text-tan underline underline-offset-2"
              >
                Retry connection
              </button>
            </div>
          </div>
        ) : null}
        {attention || later ? (
          <div className="flex w-full shrink-0 flex-col gap-2 px-4 py-2">
            {attention ? (
              <div
                data-testid="attention-alert"
                className="flex w-full items-center gap-2 border border-hairline border-l-[3px] border-l-tan bg-plate px-3 py-2 text-[13.5px] text-paper"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left hover:text-tan"
                  onClick={() => {
                    dismissedAlerts.current.add(attentionFingerprint(attention));
                    navigate(`/app/${attention.botId}`);
                    setAttention(null);
                  }}
                >
                  <span className="font-medium text-paper">{attention.title}</span>
                  {attention.body ? (
                    <span className="mt-0.5 block truncate text-[12.5px] text-mute">
                      {attention.body}
                    </span>
                  ) : null}
                </button>
                <button
                  type="button"
                  data-testid="attention-dismiss"
                  onClick={() => dismissAttention()}
                  className="shrink-0 px-2 text-[13px] text-mute hover:text-paper"
                >
                  Dismiss
                </button>
              </div>
            ) : null}
            {later ? (
              <div className="border border-hairline bg-plate px-4 py-2 text-[13.5px] text-paper">
                {later}
              </div>
            ) : null}
          </div>
        ) : null}
        <div
          ref={messageScroll}
          data-testid="thread"
          onScroll={() => {
            const element = messageScroll.current;
            if (!element) return;
            stickToLatest.current =
              element.scrollHeight - element.scrollTop - element.clientHeight < 80;
          }}
          className="ab-scroll flex min-w-0 flex-1 flex-col gap-[13px] overflow-x-hidden overflow-y-auto px-7 py-6"
        >
          {error && errorKind !== "host" ? (
            <div
              data-testid={errorKind === "auth" ? "auth-error" : "action-error"}
              className="self-center rounded-xl border border-danger/40 bg-danger-bg px-4 py-3 text-center text-[13.5px] text-danger"
            >
              <div>{error}</div>
              {errorKind === "auth" ? (
                <button
                  type="button"
                  onClick={() => void forgetDevice()}
                  className="mt-2 text-[13px] font-medium text-paper underline underline-offset-2"
                >
                  Pair this computer again
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="mt-2 text-[13px] font-medium text-paper underline underline-offset-2"
                >
                  Dismiss
                </button>
              )}
            </div>
          ) : null}
          {!active && !error && botsReady && emptyInbox === "archived" ? (
            <div
              data-testid="empty-inbox"
              className="m-auto flex max-w-sm flex-col items-center text-center"
            >
              <div className="font-display text-[17px] text-paper">Chats are archived</div>
              <p className="mt-2 text-[14px] leading-5 text-mute">
                Restore one from Archived, or create a new bot.
              </p>
              <div className="mt-5 flex gap-2">
                <Button type="button" onClick={() => setSidebarView("archived")}>
                  Open archived
                </Button>
                <Button type="button" variant="outline" onClick={() => openCreate()}>
                  Create bot
                </Button>
              </div>
            </div>
          ) : null}
          {!active && !error && botsReady && emptyInbox === "create" ? (
            <div
              data-testid="empty-bots"
              className="m-auto flex max-w-sm flex-col items-center text-center"
            >
              <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-raised text-mute">
                <IconPlus />
              </div>
              <div className="font-display text-[17px] text-paper">Create your first bot</div>
              <p className="mt-2 text-[14px] leading-5 text-mute">
                Give it a purpose, then it gets its own chat, memory, routines, and computer.
              </p>
              <Button type="button" className="mt-5" onClick={() => openCreate()}>
                Create bot
              </Button>
            </div>
          ) : null}
          {active && needsModel && !error ? (
            <div
              data-testid="needs-model"
              className="mx-4 mt-3 rounded-[12px] border border-hairline border-l-[3px] border-l-tan bg-plate px-3.5 py-3"
            >
              <p className="text-[14px] leading-5 text-paper">{NEEDS_MODEL_TEXT}</p>
              <button
                type="button"
                data-testid="open-models-thread"
                className="mt-2 text-[13px] font-medium text-tan underline underline-offset-2"
                onClick={() => openModels()}
              >
                Open Models
              </button>
            </div>
          ) : null}
          {thread?.olderCursor != null ? (
            <button
              type="button"
              data-testid="load-earlier"
              disabled={loadingOlder}
              onClick={() => void loadOlderMessages()}
              className="self-center rounded-lg px-3 py-1.5 text-[13px] text-mute hover:bg-raised hover:text-paper disabled:opacity-50"
            >
              {loadingOlder ? "Loading…" : "Load earlier messages"}
            </button>
          ) : null}
          {mergeQueuedIntoMessages(
            thread?.messages ?? [],
            offlineQueue,
            active?.id ?? "",
            thread?.threadId ?? "",
          )
            .filter((message) => !isToolNoise(message) && !isHiddenLiveDraft(message))
            .map((message) => (
              <MessageView
                key={message.id}
                canAnswer
                message={message}
                queued={isQueuedMessageId(message.id)}
                offlineCaption={offlineCaptionText(offlineCaptions, message.id)}
                runStatus={thread?.run?.status}
                onAnswer={(text) => send(text)}
                onOpenComputer={() => void openOverlay("preview")}
                onOpenBot={(id) => {
                  void refreshBots().then(() => navigate(`/app/${id}`));
                }}
                onContextMenu={(event, item) => {
                  event.preventDefault();
                  setMessageMenu({
                    message: item,
                    position: { x: event.clientX, y: event.clientY },
                  });
                }}
              />
            ))}
          {thread?.run && (thread.run.status === "failed" || thread.run.status === "cancelled") ? (
            <div
              data-testid="run-error"
              className="self-start rounded-xl border border-danger/40 bg-danger-bg px-4 py-2 text-[13.5px] text-danger"
            >
              {thread.run.error ||
                (thread.run.status === "cancelled" ? "Stopped." : "The turn failed.")}
            </div>
          ) : null}
          {thread?.run && isLiveTurn(thread.run.status) ? (
            <div className="flex justify-start">
              <div
                data-testid="typing-indicator"
                className="flex items-center gap-1.5 rounded-[18px] border border-hairline bg-plate px-4 py-3"
                title="Typing…"
              >
                <span className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan" />
                <span
                  className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan"
                  style={{ animationDelay: "150ms" }}
                />
                <span
                  className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan"
                  style={{ animationDelay: "300ms" }}
                />
              </div>
            </div>
          ) : null}
        </div>
        <div className="border-t border-hairline px-3 pb-3 pt-2.5">
          {replyTo ? (
            <div
              data-testid="reply-bar"
              className="mb-2 flex items-center gap-3 rounded-[10px] border border-hairline bg-raised px-3.5 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="text-[12px] text-mute">
                  Replying to {replyTo.role === "bot" ? active?.name || "bot" : "you"}
                </div>
                <div className="truncate text-[13.5px] text-paper">{replyExcerpt(replyTo)}</div>
              </div>
              <button
                type="button"
                className="text-mute hover:text-paper"
                aria-label="Cancel reply"
                onClick={() => setReplyTo(null)}
              >
                <IconClose />
              </button>
            </div>
          ) : null}
          <PluginsAsk
            apps={pluginApps}
            disabled={!active}
            onAsk={(name) => writeDraft(`please use ${name}`)}
          />
          {pendingFiles.length ? (
            <div className="mb-2 flex flex-wrap items-end gap-2">
              {pendingFiles.map((item) => (
                <AttachChip
                  key={item.id}
                  item={item}
                  onRemove={() =>
                    setPendingFiles((list) => list.filter((entry) => entry.id !== item.id))
                  }
                />
              ))}
            </div>
          ) : null}
          <div
            data-testid="thread-composer"
            className="flex items-end gap-2"
            onDragOver={(event) => event.preventDefault()}
            onDrop={onComposerDrop}
            onPaste={onChatPaste}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              data-testid="attach-files"
              onChange={(event) => {
                queueFiles(Array.from(event.target.files || []));
                event.target.value = "";
              }}
            />
            <button
              type="button"
              aria-label="Attach files"
              disabled={!active}
              onClick={() => fileInputRef.current?.click()}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-[8px] border border-hairline bg-raised text-paper disabled:opacity-40"
            >
              <IconPlus />
            </button>
            <textarea
              ref={composerRef}
              value={draft}
              rows={1}
              aria-label="Message"
              disabled={!active}
              onChange={(event) => writeDraft(event.target.value)}
              onPaste={onChatPaste}
              onKeyDown={(event) => onComposerKeyDown(event)}
              placeholder={
                replyTo
                  ? "Write a reply…"
                  : active
                    ? `Message ${active.name}`
                    : "Create a bot to start"
              }
              className="max-h-40 min-h-[44px] flex-1 resize-none rounded-[10px] border border-hairline bg-raised px-3 py-2.5 text-[15px] leading-[22px] text-paper disabled:cursor-not-allowed disabled:opacity-40"
            />
            {isBusy ? (
              <button
                type="button"
                data-testid="thread-stop"
                aria-label="Stop"
                onClick={() => void stop()}
                className="inline-flex h-10 items-center gap-1.5 rounded-[10px] border border-tan px-3.5 text-[13px] font-bold text-tan"
              >
                <IconStop />
                Stop
              </button>
            ) : null}
            <button
              type="button"
              aria-label="Send"
              disabled={!active || sending || !composerCanSend(draft, pendingFiles.length)}
              onClick={() => void send()}
              className="inline-flex h-10 items-center gap-1.5 rounded-[10px] bg-tan px-4 text-[13px] font-bold text-ink disabled:opacity-40"
            >
              <IconSend />
              Send
            </button>
          </div>
        </div>
      </main>

      <aside
        className={`flex h-full min-h-0 shrink-0 flex-col overflow-hidden bg-[#1a1613] transition-[width] duration-200 ease-out ${
          panel && (active || panel === "create" || panel === "models" || panel === "plugins")
            ? "w-[360px] border-l border-hairline"
            : "w-0"
        }`}
      >
        {panel && (active || panel === "create" || panel === "models" || panel === "plugins") ? (
          <div className="ab-scroll h-full w-[360px] overflow-y-auto px-4 py-3">
            {panel === "plugins" ? (
              <PluginsPane
                onClose={() => {
                  setPanel(null);
                  void refreshPlugins();
                }}
                onAppsChange={() => {
                  void refreshPlugins();
                }}
              />
            ) : null}
            {panel === "models" ? (
              <ModelsPane
                botId={active?.id}
                credentials={modelState}
                onChange={setModelState}
                onClose={closeModels}
              />
            ) : null}
            {panel === "create" ? (
              <CreateBotForm
                onCancel={() => {
                  setPanel(panelAfterCreate.current);
                  panelAfterCreate.current = null;
                }}
                onCreate={(input) => void createBot(input)}
              />
            ) : null}
            {panel === "settings" && active ? (
              <BotSettings
                bot={active}
                computer={computer ?? snapshot?.computer ?? null}
                onClose={() => setPanel(panelAfterSettings.current)}
                onUpdated={() => void refreshBots()}
                onDelete={(deleteMemories) => void deleteBot(active, deleteMemories)}
                onRestart={() => restartComputer()}
                onStop={() => stopComputer()}
                onReset={() => resetComputer()}
                onLater={setLater}
              />
            ) : null}
            {panel === "computer" && active ? (
              <ComputerPane
                bot={active}
                computer={computer ?? snapshot?.computer ?? null}
                screenUrl={screenUrl}
                screenError={screenError}
                screenEpoch={screenEpoch}
                previewFrameRef={previewFrameRef}
                booting={booting}
                onClose={() => setPanel(null)}
                onSettings={() => {
                  panelAfterSettings.current = "computer";
                  setPanel("settings");
                }}
                onOpenFullscreen={() => void openOverlay("preview")}
                onTakeControl={() => void openOverlay("button")}
                onRelease={() => void releaseComputer()}
                onRetryScreen={retryScreen}
                onScreenFrameLoad={onScreenFrameLoad}
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
              showError(err, "Failed to update pin");
            }
          }}
          onToggleUnread={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              if (target.unread) {
                heldUnreadIds.current.delete(target.id);
                await api.threads.markRead(target.id);
                patchBotUnread(target.id, false);
              } else {
                heldUnreadIds.current.add(target.id);
                await api.threads.markUnread(target.id);
                patchBotUnread(target.id, true);
              }
            } catch (err) {
              showError(err, "Failed to toggle read status");
            }
          }}
          onEdit={() => {
            const target = contextMenu.bot;
            setContextMenu(null);
            navigate(`/app/${target.id}`);
            panelAfterSettings.current = null;
            setPanel("settings");
          }}
          onDuplicate={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              const duplicated = await api.bots.duplicate(target.id);
              freshBotIds.current.add(duplicated.id);
              await refreshBots();
              navigate(`/app/${duplicated.id}`);
            } catch (err) {
              showError(err, "Duplicate failed");
            }
          }}
          onArchive={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              await api.bots.archive(target.id);
              forgetBot(target.id, active?.id === target.id);
              setArchivedBots((list) => [target, ...list.filter((item) => item.id !== target.id)]);
              await refreshBots();
            } catch (err) {
              showError(err, "Archive failed");
            }
          }}
          onDelete={async () => {
            const target = contextMenu.bot;
            setContextMenu(null);
            try {
              await api.bots.remove(target.id, false);
              forgetBot(target.id, active?.id === target.id);
              await refreshBots();
            } catch (err) {
              showError(err, "Delete failed");
            }
          }}
        />
      ) : null}

      <ComputerOverlay
        booting={booting}
        open={computerOpen}
        bot={active}
        computer={computer}
        screenUrl={screenUrl}
        screenError={screenError}
        screenEpoch={screenEpoch}
        overlayFrameRef={overlayFrameRef}
        onRelease={() => void releaseComputer()}
        onTakeControl={() => void bootComputer({ takeControl: true, overlay: false })}
        onClose={() => setComputerOpen(false)}
        onRetry={retryScreen}
        onScreenFrameLoad={onScreenFrameLoad}
        onScreenError={(message) => setScreenError(message)}
      />
    </div>
  );
}

function AttachChip({ item, onRemove }: { item: PendingFile; onRemove: () => void }) {
  const kind = previewKind(item.file);
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (kind === "file") return;
    const next = URL.createObjectURL(item.file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [item.file, kind]);

  return (
    <span
      data-testid="attach-chip"
      data-kind={kind}
      className="flex max-w-full items-center gap-2 rounded-xl border border-hairline bg-raised px-2 py-1.5 text-[13px] text-paper"
    >
      {kind === "image" && url ? (
        <img
          data-testid="attach-preview"
          src={url}
          alt={item.file.name}
          className="h-14 w-14 shrink-0 rounded-lg object-cover"
        />
      ) : null}
      {kind === "video" && url ? (
        <video
          data-testid="attach-preview"
          src={url}
          controls
          preload="metadata"
          className="h-20 max-w-[200px] shrink-0 rounded-lg"
        />
      ) : null}
      {kind === "audio" && url ? (
        <audio data-testid="attach-preview" src={url} controls className="h-8 max-w-[220px]" />
      ) : null}
      <span className="max-w-[140px] truncate">{item.file.name}</span>
      <button
        type="button"
        aria-label={`Remove ${item.file.name}`}
        className="text-mute hover:text-paper"
        onClick={onRemove}
      >
        ✕
      </button>
    </span>
  );
}

function hasLive(snapshot: ThreadSnapshot): boolean {
  return snapshot.messages.some(
    (message) =>
      message.id.startsWith("stream:") &&
      message.blocks.some((b) => b.kind === "progress" && Boolean(b.text)),
  );
}

function offlineCaptionText(captions: OfflineCaption[], messageId: string): string | undefined {
  const caption = captionForMessage(captions, messageId);
  return caption ? formatOfflineCaption(caption.queuedAt) : undefined;
}

function hasActiveWorkers(snapshot: ThreadSnapshot): boolean {
  if (
    (snapshot.subagents ?? []).some((item) => item.status === "queued" || item.status === "running")
  ) {
    return true;
  }
  return snapshot.messages.some((message) =>
    message.blocks.some(
      (block) =>
        block.kind === "subagent" && (block.status === "queued" || block.status === "running"),
    ),
  );
}
