import {
  type ClipboardEvent,
  type Dispatch,
  type DragEvent,
  type KeyboardEvent,
  type SetStateAction,
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
  alertKeysToRemember,
  allowAlert,
  answeredAskBody,
  attentionFingerprint,
  attentionFromEvent,
  desktopWindowFocused,
  isHistoricalEvent,
  nativeNotifyTag,
  parkedAttentionForView,
  rememberShownAlert,
  shouldClearAttentionForView,
  shouldConsiderEventForAttention,
  shouldCountThreadRead,
  shouldReplaceAttention,
  shouldSendDesktopAlert,
  shouldSendNativeAlert,
  shouldStickDismissOnView,
  shouldWatchBackgroundBot,
} from "../lib/alerts";
import { healthOkClearsError, workspaceEventsAuthLoss } from "../lib/auth-loss";
import { composerCanSend, composerPlaceholder, composerShouldSend } from "../lib/composer";
import {
  applyComposerSendResult,
  type ComposerSlot,
  emptyComposerSlot,
} from "../lib/composer-slots";
import {
  composerRedo,
  composerUndo,
  composerUndoKind,
  createComposerHistory,
  pushComposerChange,
  resetComposerHistory,
} from "../lib/composer-undo";
import {
  fulfillOwnerJob,
  isAutoOwnerJob,
  pendingOwnerJobIds,
  shouldAutoFulfillOwnerJob,
} from "../lib/consent";
import { copyText } from "../lib/copy-text";
import { hatchIsOpen, hatchPointerEvents } from "../lib/hatch";
import { inFlightProgressText } from "../lib/in-flight-status";
import { contextLinkUrl, stripMarkdown } from "../lib/markdown";
import { dispatchMemoryChanged } from "../lib/memory";
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
import { openOwnerBrowser } from "../lib/owner-browser";
import { panelEscapeAction } from "../lib/panel-escape";
import {
  nextPhoneTab,
  type PhoneTab,
  phoneTabAfterPanel,
  shouldUsePhoneDeskControls,
  shouldUsePhoneShell,
} from "../lib/phone-shell";
import { ownerRunError } from "../lib/run-error";
import {
  embeddableScreenUrl,
  screenFrameLooksFailed,
  screenPolicy,
  shouldFetchScreenUrl,
  shouldKeepScreenUrlOnRelease,
  shouldRefreshScreenUrl,
  shouldReplaceScreenUrl,
  shouldTakeControl,
} from "../lib/screen";
import {
  filterBots,
  inboxEmptyState,
  inboxFallbackPath,
  type SidebarView,
  sortInboxBots,
} from "../lib/sidebar";
import {
  canAnswerOwnerPrompt,
  isHiddenLiveDraft,
  isRawRunFailedMessage,
  isToolNoise,
} from "../lib/thread-events";
import {
  applyOlderPageForBot,
  applySnapshotForBot,
  createThreadSnapshotCache,
  forgetThread,
  peekThread,
  rememberThread,
  touchThread,
} from "../lib/thread-snapshot-cache";
import {
  addPendingFiles,
  clipboardFilePaths,
  clipboardPrefersImage,
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
import {
  isIosDevice,
  isStandaloneDisplay,
  pageSurface,
  pairAgainLabel,
  shouldHoldHostAlert,
  shouldOfferWebAlerts,
  shouldShowWebNotification,
  webNotificationBody,
} from "../lib/web-notify";
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
import { HostPhoneBanners } from "./shell/HostPhoneBanners";
import { InboxList } from "./shell/InboxList";
import { MessageView, messageCopyText, replyExcerpt } from "./shell/MessageView";
import { ModelsPane } from "./shell/ModelsPane";
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
  const [phoneTab, setPhoneTab] = useState<PhoneTab>("chat");
  const [phoneShell, setPhoneShell] = useState(() =>
    typeof window === "undefined"
      ? false
      : shouldUsePhoneShell(window.innerWidth, window.innerHeight),
  );
  const [phoneDesk, setPhoneDesk] = useState(() =>
    typeof window === "undefined"
      ? false
      : shouldUsePhoneDeskControls(window.matchMedia("(hover: hover) and (pointer: fine)").matches),
  );
  const [memoryFocusFact, setMemoryFocusFact] = useState<string | null>(null);
  const [alertOffer, setAlertOffer] = useState<"hide" | "ask" | "ready">(() =>
    shouldOfferWebAlerts({
      surface: pageSurface(),
      permission: typeof Notification === "undefined" ? "unsupported" : Notification.permission,
      standalone: isStandaloneDisplay(),
      ios: isIosDevice(),
    }),
  );
  const [homeHintDismissed, setHomeHintDismissed] = useState(() => {
    try {
      return localStorage.getItem("artek-home-screen-hint") === "1";
    } catch {
      return false;
    }
  });
  const [snapshot, setSnapshot] = useState<ThreadSnapshot | null>(null);
  const [draft, setDraft] = useState("");
  const draftHistory = useRef(createComposerHistory(""));
  const draftChangeAt = useRef(0);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [sending, setSending] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
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
  const [threadAtStart, setThreadAtStart] = useState(false);
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
  const prevBotsRef = useRef(new Map<string, Bot>());
  const activeIdRef = useRef<string | undefined>(undefined);
  const botIdRef = useRef<string | undefined>(undefined);
  const requestedBotId = useRef<string | null>(null);
  const inboxPointerDown = useRef<string | null>(null);
  const botsRef = useRef<Bot[]>([]);
  const windowFocusedRef = useRef(true);
  const gtkActiveRef = useRef<boolean | null>(null);
  const [windowFocused, setWindowFocused] = useState(true);
  const [pageHidden, setPageHidden] = useState(false);
  const shellOpenedAt = useRef(Date.now());
  const freshBotIds = useRef(new Set<string>());
  const previousViewingRef = useRef<string | null>(null);
  const refreshBotsRef = useRef<() => Promise<Bot[]>>(async () => []);
  const considerEventRef = useRef<
    (
      incoming: ProductEvent,
      bot: Bot,
      opts?: { live?: boolean; source?: "thread" | "workspace" },
    ) => void
  >(() => undefined);
  const [contextMenu, setContextMenu] = useState<{
    bot: Bot;
    position: ContextMenuPosition;
  } | null>(null);
  const [messageMenu, setMessageMenu] = useState<{
    message: ThreadMessage;
    position: ContextMenuPosition;
    url?: string;
  } | null>(null);
  const [replyTo, setReplyTo] = useState<ThreadMessage | null>(null);
  const composerSlots = useRef(new Map<string, ComposerSlot<ThreadMessage>>());
  const composerBotRef = useRef<string | undefined>(undefined);
  const threadCache = useRef(createThreadSnapshotCache());
  const discardedBotIds = useRef(new Set<string>());
  const heldUnreadIds = useRef(new Set<string>());
  const messageScroll = useRef<HTMLDivElement>(null);

  const active = bots.find((bot) => bot.id === botId);
  activeIdRef.current = active?.id;
  botIdRef.current = botId;
  const cachedEntry = active ? peekThread(threadCache.current, active.id) : undefined;
  const cachedSnapshot = cachedEntry?.snapshot ?? null;
  const thread = active && snapshot?.botId === active.id ? snapshot : cachedSnapshot;
  const historyAtStart =
    snapshot?.botId === active?.id ? threadAtStart : Boolean(cachedEntry?.atStart);
  const loadingThread = Boolean(active && !thread && !error);
  const isParked = thread?.run?.status === "waiting_takeover";
  const isBusy = Boolean(
    (thread?.run && isLiveTurn(thread.run.status)) ||
      (thread && !isParked && (hasLive(thread) || hasActiveWorkers(thread))),
  );
  const flightText = inFlightProgressText(thread?.subagents);

  useEffect(() => {
    botsRef.current = bots;
  }, [bots]);

  useEffect(() => {
    function applyFocus() {
      const hidden = document.hidden;
      const focused = desktopWindowFocused({
        gtkActive: gtkActiveRef.current,
        pageHidden: hidden,
        browserFocused: document.visibilityState === "visible" && document.hasFocus(),
      });
      windowFocusedRef.current = focused;
      setWindowFocused(focused);
      setPageHidden(hidden);
    }
    function onGtkActive(active: boolean | number) {
      gtkActiveRef.current = Boolean(active);
      applyFocus();
    }
    applyFocus();
    window.addEventListener("focus", applyFocus);
    window.addEventListener("blur", applyFocus);
    document.addEventListener("visibilitychange", applyFocus);
    const win = window as Window & {
      __artekSetWindowActive?: (active: boolean | number) => void;
    };
    win.__artekSetWindowActive = onGtkActive;
    return () => {
      window.removeEventListener("focus", applyFocus);
      window.removeEventListener("blur", applyFocus);
      document.removeEventListener("visibilitychange", applyFocus);
      delete win.__artekSetWindowActive;
    };
  }, []);

  useEffect(() => {
    filesEpoch.current += 1;
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
    if (pageSurface() === "desktop") {
      void api.local.dismissNotify(nativeNotifyTag(id));
    }
  }

  async function readGtkWindowActive(): Promise<boolean | null> {
    if (pageSurface() !== "desktop") return gtkActiveRef.current;
    try {
      const status = await api.local.status();
      if (status.windowActive === true || status.windowActive === false) {
        gtkActiveRef.current = status.windowActive;
        const hidden = typeof document !== "undefined" && document.hidden;
        const focused = desktopWindowFocused({
          gtkActive: status.windowActive,
          pageHidden: hidden,
          browserFocused:
            typeof document !== "undefined" &&
            document.visibilityState === "visible" &&
            document.hasFocus(),
        });
        windowFocusedRef.current = focused;
        setWindowFocused(focused);
        setPageHidden(hidden);
        return status.windowActive;
      }
    } catch {
      /* loopback down */
    }
    return gtkActiveRef.current;
  }

  useEffect(() => {
    if (!botId) return;
    void (async () => {
      const gtkWindowActive = await readGtkWindowActive();
      if (
        !shouldCountThreadRead({
          viewingBotId: botId,
          chatId: botId,
          windowFocused,
          pageHidden,
          gtkWindowActive,
        })
      ) {
        return;
      }
      markOpenThreadRead(botId);
    })();
  }, [botId, windowFocused, pageHidden]);

  async function dispatchAlert(next: AttentionAlert, key: string, notifyOnFinish: boolean) {
    if (!allowAlert(next, notifyOnFinish)) return;
    const fingerprint = attentionFingerprint(next);
    if (seenAlertKeys.current.has(key) || seenAlertKeys.current.has(fingerprint)) return;
    if (dismissedAlerts.current.has(fingerprint)) {
      seenAlertKeys.current.add(key);
      seenAlertKeys.current.add(fingerprint);
      return;
    }
    const gtkWindowActive = await readGtkWindowActive();
    if (seenAlertKeys.current.has(key) || seenAlertKeys.current.has(fingerprint)) return;
    const viewing = activeIdRef.current || botIdRef.current || null;
    const hidden = typeof document !== "undefined" && document.hidden;
    const surface = pageSurface();
    const showBanner = shouldSendDesktopAlert({
      windowFocused: true,
      viewingBotId: viewing,
      alertBotId: next.botId,
    });
    const showNative =
      surface === "desktop" &&
      shouldSendNativeAlert({
        gtkWindowActive,
        windowFocused: windowFocusedRef.current && !hidden,
        viewingBotId: viewing,
        alertBotId: next.botId,
        pageHidden: hidden,
      });
    const showWeb =
      surface === "host" &&
      shouldShowWebNotification({
        pageHidden: hidden,
        viewingBotId: viewing,
        alertBotId: next.botId,
      });
    if (
      surface === "host" &&
      shouldHoldHostAlert({ pageHidden: hidden, viewingBotId: viewing, alertBotId: next.botId })
    ) {
      const held = pendingAlerts.current.get(next.botId);
      if (!held || shouldReplaceAttention(held.alert, next)) {
        pendingAlerts.current.set(next.botId, { alert: next, notifyOnFinish, key });
      }
      return;
    }
    const surfaced = showBanner || showNative || showWeb;
    if (!surfaced) return;
    if (rememberShownAlert(seenAlertKeys.current, key) === "skip") return;
    for (const item of alertKeysToRemember({
      key,
      fingerprint,
      botId: next.botId,
      kind: next.kind,
      surfaced: true,
    })) {
      seenAlertKeys.current.add(item);
    }
    if (seenAlertKeys.current.size > 250) {
      const oldest = seenAlertKeys.current.values().next().value;
      if (oldest) seenAlertKeys.current.delete(oldest);
    }
    pendingAlerts.current.delete(next.botId);
    if (showBanner) {
      setAttention((current) => (shouldReplaceAttention(current, next) ? next : current));
    }
    if (showNative) {
      void api.local.notify({
        title: next.title,
        body: next.body,
        urgency: next.urgency,
        tag: nativeNotifyTag(next.botId),
      });
    }
    if (showWeb) {
      raiseWebNotification(next);
    }
  }

  function raiseWebNotification(next: AttentionAlert) {
    if (pageSurface() !== "host") return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    try {
      const note = new Notification(next.title, {
        body: webNotificationBody(next),
        tag: next.botId,
      });
      note.onclick = () => {
        window.focus();
        openBot(next.botId);
        note.close();
      };
    } catch {
      /* iOS ignores Notification if the home-screen app is not allowed */
    }
  }

  function flushHeldWebAlerts() {
    if (typeof document === "undefined" || !document.hidden) return;
    const viewing = activeIdRef.current || botIdRef.current || null;
    for (const [id, held] of [...pendingAlerts.current.entries()]) {
      if (
        !shouldShowWebNotification({
          pageHidden: true,
          viewingBotId: viewing,
          alertBotId: id,
        })
      ) {
        continue;
      }
      pendingAlerts.current.delete(id);
      rememberShownAlert(seenAlertKeys.current, held.key);
      seenAlertKeys.current.add(attentionFingerprint(held.alert));
      raiseWebNotification(held.alert);
    }
  }

  function flushHeldAlerts() {
    const viewing = activeIdRef.current || botIdRef.current || null;
    for (const [id, held] of [...pendingAlerts.current.entries()]) {
      if (id === viewing) continue;
      pendingAlerts.current.delete(id);
      void dispatchAlert(held.alert, held.key, held.notifyOnFinish);
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
    void dispatchAlert(next, `${next.botId}:${next.kind}:parked`, source?.notifyOnFinish ?? true);
  }

  function openBot(id: string) {
    requestedBotId.current = id;
    activeIdRef.current = id;
    botIdRef.current = id;
    setPhoneTab(nextPhoneTab("select-bot"));
    navigate(`/app/${id}`);
  }

  function dismissAttention(alert: AttentionAlert | null = attention) {
    if (alert) {
      dismissedAlerts.current.add(attentionFingerprint(alert));
      pendingAlerts.current.delete(alert.botId);
      if (pageSurface() === "desktop") {
        void api.local.dismissNotify(nativeNotifyTag(alert.botId));
      }
    }
    setAttention(null);
  }

  function startOwnerFulfill(consentId: string) {
    if (!consentId || fulfilledOwnerJobs.current.has(consentId)) return;
    if (!shouldAutoFulfillOwnerJob(pageSurface())) return;
    fulfilledOwnerJobs.current.add(consentId);
    void fulfillOwnerJob(consentId).catch(() => {
      fulfilledOwnerJobs.current.delete(consentId);
    });
  }

  function considerEvent(
    incoming: ProductEvent,
    bot: Bot,
    opts?: { live?: boolean; source?: "thread" | "workspace" },
  ) {
    const granted = isAutoOwnerJob(incoming);
    if (granted) startOwnerFulfill(granted.consentId);
    dispatchMemoryChanged(incoming.type);
    if (!opts?.live && isHistoricalEvent(incoming, shellOpenedAt.current)) return;
    const next = shouldConsiderEventForAttention(opts?.source ?? "thread")
      ? attentionFromEvent(incoming, bot.name)
      : null;
    const answered = answeredAskBody(incoming);
    if (answered) {
      const held = pendingAlerts.current.get(bot.id);
      if (held?.alert.kind === "ask") {
        dismissedAlerts.current.add(attentionFingerprint(held.alert));
      }
      pendingAlerts.current.delete(bot.id);
      setAttention((current) => {
        if (current?.botId !== bot.id || current.kind !== "ask") return current;
        dismissedAlerts.current.add(attentionFingerprint(current));
        return null;
      });
    }
    flushHeldAlerts();
    if (next) void dispatchAlert(next, incoming.id, bot.notifyOnFinish);
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
    if (pageSurface() !== "host") return;
    function onHide() {
      if (typeof document !== "undefined" && document.hidden) {
        flushHeldWebAlerts();
      }
    }
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onHide);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onHide);
    };
  }, []);

  useEffect(() => {
    const viewing = activeIdRef.current || botIdRef.current || null;
    const lookingAtThread =
      viewing != null &&
      shouldCountThreadRead({
        viewingBotId: viewing,
        chatId: viewing,
        windowFocused,
        pageHidden,
        gtkWindowActive: gtkActiveRef.current,
      });
    if (lookingAtThread && shouldClearAttentionForView(attention, viewing)) {
      if (shouldStickDismissOnView(attention, viewing, previousViewingRef.current)) {
        dismissedAlerts.current.add(attentionFingerprint(attention));
      }
      setAttention(null);
    }
    previousViewingRef.current = viewing;
  }, [active?.id, attention, windowFocused, pageHidden]);

  async function refreshBots() {
    const list = await api.bots.list();
    const viewing = activeIdRef.current || botIdRef.current;
    const gtkWindowActive = await readGtkWindowActive();
    if (
      viewing &&
      !heldUnreadIds.current.has(viewing) &&
      shouldCountThreadRead({
        viewingBotId: viewing,
        chatId: viewing,
        windowFocused: windowFocusedRef.current,
        pageHidden: typeof document !== "undefined" && document.hidden,
        gtkWindowActive,
      })
    ) {
      const open = list.find((item) => item.id === viewing);
      if (open?.unread) {
        open.unread = false;
        markOpenThreadRead(viewing);
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
    setPhoneTab(nextPhoneTab("open-desk"));
    setPanel("models");
  }

  function closeModels() {
    const restore = panelAfterModels.current;
    panelAfterModels.current = null;
    setPanel(restore);
    if (phoneShell) setPhoneTab(phoneTabAfterPanel(restore));
  }

  function closeSettings() {
    const restore = panelAfterSettings.current;
    panelAfterSettings.current = null;
    setPanel(restore);
    if (phoneShell) setPhoneTab(phoneTabAfterPanel(restore));
  }

  function closeCreate() {
    const restore = panelAfterCreate.current;
    panelAfterCreate.current = null;
    setPanel(restore);
    if (phoneShell) setPhoneTab(phoneTabAfterPanel(restore));
  }

  function openPlugins() {
    setPhoneTab(nextPhoneTab("open-desk"));
    setPanel("plugins");
  }

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
      if (healthOkClearsError(errorKindRef.current)) {
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
    if (activeIdRef.current === botId) {
      setReplyTo(null);
    } else {
      const parked = composerSlots.current.get(botId) ?? emptyComposerSlot<ThreadMessage>();
      composerSlots.current.set(botId, { ...parked, replyTo: null, sending: false });
    }
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
      setSending(false);
    }
    composerSlots.current.delete(id);
    forgetThread(threadCache.current, id);
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

  function cacheSnapshot(action: SetStateAction<ThreadSnapshot | null>) {
    setSnapshot((prev) => {
      const next = typeof action === "function" ? action(prev) : action;
      if (next?.botId) {
        const held = threadCache.current.get(next.botId);
        rememberThread(threadCache.current, next.botId, {
          snapshot: next,
          preserveLoadedHistory: held?.preserveLoadedHistory ?? false,
          atStart: held?.atStart ?? false,
        });
      }
      return next;
    });
  }

  const publishSnapshot: Dispatch<SetStateAction<ThreadSnapshot | null>> = cacheSnapshot;

  async function refreshThread(id: string) {
    if (discardedBotIds.current.has(id)) return null;
    const viewing = activeIdRef.current === id;
    const scrollElement = viewing ? messageScroll.current : null;
    const stickToEnd =
      !scrollElement ||
      scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight < 80;
    const snap = await api.threads.get(id);
    if (discardedBotIds.current.has(id) || snap.botId !== id) return snap;
    const entry = applySnapshotForBot(threadCache.current, id, snap);
    if (!entry || activeIdRef.current !== id) return snap;
    setSnapshot(entry.snapshot);
    setThreadAtStart(entry.atStart);
    setComputer(snap.computer);
    for (const consentId of pendingOwnerJobIds(snap)) startOwnerFulfill(consentId);
    if (stickToEnd) {
      window.requestAnimationFrame(() => {
        const element = messageScroll.current;
        if (element) element.scrollTop = element.scrollHeight;
      });
    }
    return snap;
  }

  async function loadOlderMessages() {
    const requested = active?.id;
    const cursor = thread?.olderCursor;
    if (!requested || cursor == null || loadingOlder) return;
    const scrollElement = messageScroll.current;
    const previousHeight = scrollElement?.scrollHeight ?? 0;
    setLoadingOlder(true);
    try {
      const page = await api.threads.messages(requested, cursor);
      const entry = applyOlderPageForBot(threadCache.current, requested, page);
      if (!entry || activeIdRef.current !== requested) return;
      setSnapshot(entry.snapshot);
      if (entry.atStart) setThreadAtStart(true);
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
    const listedIds = bots.map((bot) => bot.id);
    if (botId && listedIds.includes(botId) && requestedBotId.current === botId) {
      requestedBotId.current = null;
    }
    const next = inboxFallbackPath(
      botId,
      listedIds,
      sortInboxBots(bots)[0]?.id,
      requestedBotId.current,
    );
    if (next) navigate(next, { replace: true });
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
    const cached = touchThread(threadCache.current, active.id);
    setSnapshot(cached?.snapshot ?? null);
    setThreadAtStart(cached?.atStart ?? false);
    setComputer(cached?.snapshot.computer ?? null);
    setLoadingOlder(false);
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
              applyThreadEvent(event, publishSnapshot, setComputer);
            }
            const bot = botsRef.current.find((item) => item.id === active.id) ?? active;
            considerEvent(event, bot, { source: "thread" });
            if (leftChat) break;
            if (event.type === "run.completed" || event.type === "run.failed") {
              void refreshBotsRef.current().catch(() => undefined);
              void refreshThread(active.id).catch(() => undefined);
            }
          }
        } catch (err) {
          if (abort.signal.aborted) break;
          const classified = classifyError(err);
          if (workspaceEventsAuthLoss(err) === "repair") {
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
            if (bot) {
              considerEventRef.current(event, bot, { live: true, source: "workspace" });
            }
          }
        } catch (err) {
          if (abort.signal.aborted) break;
          const classified = classifyError(err);
          if (workspaceEventsAuthLoss(err) === "repair") {
            showError(err, classified.message);
            break;
          }
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
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape" || event.isComposing) return;
      const action = panelEscapeAction({ computerOpen, panel });
      if (action === "close-overlay") {
        event.preventDefault();
        setComputerOpen(false);
        return;
      }
      if (action === "close-settings") {
        event.preventDefault();
        closeSettings();
        return;
      }
      if (action === "close-create") {
        event.preventDefault();
        closeCreate();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [computerOpen, panel, phoneShell]);

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
  const hatchOpen = hatchIsOpen(panel, Boolean(active));

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

  useLayoutEffect(() => {
    const prev = composerBotRef.current;
    if (prev && prev !== botId) {
      composerSlots.current.set(prev, {
        draft,
        history: draftHistory.current,
        pendingFiles,
        sending,
        replyTo,
      });
    }
    composerBotRef.current = botId;
    const parked = botId ? composerSlots.current.get(botId) : undefined;
    const next = parked ?? emptyComposerSlot<ThreadMessage>();
    draftHistory.current = next.history;
    draftChangeAt.current = 0;
    setDraft(next.draft);
    setPendingFiles(next.pendingFiles);
    setSending(next.sending);
    setReplyTo(next.replyTo);
    window.requestAnimationFrame(() => sizeComposer());
  }, [botId]);

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
    if (composerShouldSend(event)) {
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
      __artekComposerUndo?: () => void;
      __artekComposerRedo?: () => void;
      __artekSetWindowActive?: (active: boolean | number) => void;
    };
    win.__artekAttachPastedImage = (contentBase64, type, name) => {
      queueFilesRef.current(filesFromAttachedPayload([{ name, type, contentBase64 }]));
    };
    win.__artekComposerUndo = () => {
      const next = composerUndo(draftHistory.current);
      if (!next) return;
      draftHistory.current = next.history;
      setDraft(next.value);
      window.requestAnimationFrame(() => sizeComposer());
    };
    win.__artekComposerRedo = () => {
      const next = composerRedo(draftHistory.current);
      if (!next) return;
      draftHistory.current = next.history;
      setDraft(next.value);
      window.requestAnimationFrame(() => sizeComposer());
    };
    return () => {
      delete win.__artekAttachPastedImage;
      delete win.__artekComposerUndo;
      delete win.__artekComposerRedo;
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
    if (!clipboardPrefersImage(wrapped)) {
      const paths = clipboardFilePaths(wrapped);
      if (paths.length) {
        attachLocalPaths(paths);
        return;
      }
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
      const next = applyComposerSendResult({
        currentBotId: activeIdRef.current,
        targetId,
        live: {
          draft,
          history: draftHistory.current,
          pendingFiles,
          sending: true,
          replyTo,
        },
        parked: composerSlots.current.get(targetId),
        result: { ok: true },
      });
      if (activeIdRef.current === targetId) {
        setReplyTo(null);
      } else if (next.parked) {
        composerSlots.current.set(targetId, next.parked);
      }
    } catch (err) {
      const classified = classifyError(err);
      if (shouldQueueSend(classified.kind)) {
        parkSend(targetId, text, replyId, attachments);
        return;
      }
      const next = applyComposerSendResult({
        currentBotId: activeIdRef.current,
        targetId,
        live: {
          draft,
          history: draftHistory.current,
          pendingFiles,
          sending: true,
          replyTo,
        },
        parked: composerSlots.current.get(targetId),
        result: { ok: false, draft: text, files },
      });
      if (activeIdRef.current === targetId) {
        if (textOverride == null) {
          writeDraft(text);
          setPendingFiles(files);
        }
      } else if (next.parked) {
        composerSlots.current.set(targetId, next.parked);
      }
      showError(err, "Send failed");
      return;
    } finally {
      if (activeIdRef.current === targetId) {
        setSending(false);
      } else {
        const parked = composerSlots.current.get(targetId);
        if (parked) {
          composerSlots.current.set(targetId, { ...parked, sending: false });
        }
      }
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
    force = false,
  }: {
    takeControl: boolean;
    force?: boolean;
  }): Promise<boolean> {
    if (!active) return false;
    sleepHeld.current = false;
    const needsBoot = force || computer?.state !== "running" || !screenUrlRef.current;
    if (needsBoot) setBooting(true);
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
      force: computer?.state !== "running",
    });
    if (ok) setComputerOpen(true);
  }

  async function releaseComputer() {
    if (!active) return;
    if (!shouldKeepScreenUrlOnRelease() && screenPolicy(screenUrlRef.current) === "control") {
      adoptScreenUrl(null);
      setScreenEpoch((value) => value + 1);
    }
    await api.computer.release(active.id).catch(() => undefined);
    const status = await api.computer.status(active.id).catch(() => null);
    if (status) {
      setComputer(status);
      setSnapshot((prev) => {
        if (!prev) return prev;
        const next = { ...prev, computer: status };
        const held = threadCache.current.get(prev.botId);
        rememberThread(threadCache.current, prev.botId, {
          snapshot: next,
          preserveLoadedHistory: held?.preserveLoadedHistory ?? false,
          atStart: held?.atStart ?? false,
        });
        return next;
      });
    }
    await ensureScreenUrl(active.id, true, true);
  }

  async function createBot(input: {
    name: string;
    title: string;
    description: string;
    instructions: string;
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
        instructions: input.instructions,
        computerMode: input.computerMode,
      });
      freshBotIds.current.add(bot.id);
      await refreshBots();
      setPhoneTab(nextPhoneTab("select-bot"));
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
    setPhoneTab(nextPhoneTab("open-desk"));
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

  useLayoutEffect(() => {
    function apply() {
      setPhoneShell(shouldUsePhoneShell(window.innerWidth, window.innerHeight));
      setPhoneDesk(
        shouldUsePhoneDeskControls(window.matchMedia("(hover: hover) and (pointer: fine)").matches),
      );
    }
    apply();
    const mouseDesktop = window.matchMedia("(hover: hover) and (pointer: fine)");
    mouseDesktop.addEventListener("change", apply);
    window.addEventListener("resize", apply);
    window.addEventListener("orientationchange", apply);
    return () => {
      mouseDesktop.removeEventListener("change", apply);
      window.removeEventListener("resize", apply);
      window.removeEventListener("orientationchange", apply);
    };
  }, []);

  return (
    <div
      className="relative flex h-full min-w-0 flex-col overflow-hidden bg-ink text-paper"
      data-surface={pageSurface()}
      data-phone-tab={phoneTab}
      data-phone-shell={phoneShell ? "1" : "0"}
      data-desk-overlay={computerOpen ? "1" : "0"}
    >
      <HostPhoneBanners
        alertOffer={alertOffer}
        hintDismissed={homeHintDismissed}
        onDismissHint={() => {
          setHomeHintDismissed(true);
          try {
            localStorage.setItem("artek-home-screen-hint", "1");
          } catch {
            /* private mode */
          }
        }}
        onAlertPermission={(permission) => {
          setAlertOffer(
            shouldOfferWebAlerts({
              surface: pageSurface(),
              permission,
              standalone: isStandaloneDisplay(),
              ios: isIosDevice(),
            }),
          );
        }}
      />
      <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <aside
          data-shell="rack"
          data-phone-show={phoneTab === "chats" ? "1" : "0"}
          className="flex w-[252px] shrink-0 flex-col border-r border-hairline bg-ink"
        >
          <div className="app-drag flex items-center justify-between px-3 pb-2 pt-3">
            {pageSurface() === "host" ? (
              <span className="text-[13px] text-mute">Artek Buddy</span>
            ) : (
              <WindowChrome />
            )}
          </div>
          <div className="mb-2 flex items-center gap-2 px-3">
            <label className="flex min-w-0 flex-1 items-center gap-2 rounded-[8px] border border-hairline bg-raised px-2.5 py-1.5 text-[14px] text-mute">
              <IconSearch />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search"
                aria-label="Search inbox"
                className="w-full min-w-0 bg-transparent"
              />
              {query.trim() ? (
                <button
                  type="button"
                  data-testid="inbox-search-clear"
                  aria-label="Clear Search"
                  onClick={() => setQuery("")}
                  className="shrink-0 text-[13px] text-mute hover:text-paper"
                >
                  ×
                </button>
              ) : null}
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
            <InboxList
              sidebarView={sidebarView}
              query={query}
              bots={filtered}
              archived={filteredArchived}
              archivedCount={archivedBots.length}
              activeId={active?.id}
              inboxPointerDown={inboxPointerDown}
              onBackInbox={() => setSidebarView("inbox")}
              onRestore={(bot) => void restoreBot(bot)}
              onOpenBot={(id) => openBot(id)}
              onContextMenu={(bot, event) => {
                setContextMenu({
                  bot,
                  position: { x: event.clientX, y: event.clientY },
                });
              }}
              onOpenArchived={() => setSidebarView("archived")}
            />
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
          data-phone-show={phoneTab === "chat" ? "1" : "0"}
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
                onClick={() => {
                  if (panel === "computer") {
                    setPanel(null);
                    if (phoneShell) setPhoneTab(nextPhoneTab("close-desk"));
                    return;
                  }
                  setPhoneTab(nextPhoneTab("open-desk"));
                  setPanel("computer");
                }}
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
                  setPhoneTab(nextPhoneTab("open-desk"));
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
                    className="relative z-0 min-w-0 flex-1 text-left hover:text-tan"
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
                    onPointerDown={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                    }}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      dismissAttention();
                    }}
                    className="relative z-10 shrink-0 px-2 text-[13px] text-mute hover:text-paper"
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
          {error && errorKind !== "host" ? (
            <div
              data-testid={errorKind === "auth" ? "auth-error" : "action-error"}
              className="mx-4 mt-2 shrink-0 self-center rounded-xl border border-danger/40 bg-danger-bg px-4 py-3 text-center text-[13.5px] text-danger"
            >
              <div>{error}</div>
              {errorKind === "auth" ? (
                <button
                  type="button"
                  onClick={() => void forgetDevice()}
                  className="mt-2 text-[13px] font-medium text-paper underline underline-offset-2"
                >
                  {pairAgainLabel()}
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
            {loadingThread ? (
              <div
                data-testid="thread-loading"
                role="status"
                aria-live="polite"
                className="m-auto max-w-sm text-center text-[14px] leading-5 text-mute"
              >
                Loading this chat…
              </div>
            ) : null}
            {!loadingThread && thread?.olderCursor != null ? (
              <button
                type="button"
                data-testid="load-earlier"
                aria-label="Load earlier messages"
                disabled={loadingOlder}
                onClick={() => void loadOlderMessages()}
                className="self-center rounded-lg border border-hairline px-3 py-1.5 text-[13px] text-paper hover:bg-raised disabled:opacity-50"
              >
                {loadingOlder ? "Loading…" : "Load earlier messages"}
              </button>
            ) : !loadingThread && historyAtStart ? (
              <p data-testid="thread-start" className="self-center text-[13px] text-mute">
                Beginning of this chat.
              </p>
            ) : null}
            {mergeQueuedIntoMessages(
              thread?.messages ?? [],
              offlineQueue,
              active?.id ?? "",
              thread?.threadId ?? "",
            )
              .filter(
                (message) =>
                  !isToolNoise(message) &&
                  !isHiddenLiveDraft(message) &&
                  !isRawRunFailedMessage(message),
              )
              .map((message) => (
                <MessageView
                  key={message.id}
                  canAnswer={canAnswerOwnerPrompt(message, thread?.run)}
                  message={message}
                  queued={isQueuedMessageId(message.id)}
                  offlineCaption={offlineCaptionText(offlineCaptions, message.id)}
                  runStatus={thread?.run?.status}
                  onAnswer={async (text, item) => {
                    if (!active || !item.runId) {
                      throw new Error("This question is no longer waiting");
                    }
                    await api.threads.answer(active.id, item.runId, item.id, text);
                  }}
                  onOpenComputer={() => void openOverlay("preview")}
                  onOpenMemory={(fact) => {
                    setMemoryFocusFact(fact);
                    setPanel("computer");
                    if (phoneShell) setPhoneTab(nextPhoneTab("open-desk"));
                  }}
                  onOpenBot={(id) => {
                    void refreshBots().then(() => navigate(`/app/${id}`));
                  }}
                  onContextMenu={(event, item) => {
                    event.preventDefault();
                    setMessageMenu({
                      message: item,
                      position: { x: event.clientX, y: event.clientY },
                      url: contextLinkUrl(event.target),
                    });
                  }}
                />
              ))}
            {thread?.run &&
            (thread.run.status === "failed" || thread.run.status === "cancelled") ? (
              <div
                data-testid="run-error"
                className="self-start rounded-xl border border-danger/40 bg-danger-bg px-4 py-2 text-[13.5px] text-danger"
              >
                {ownerRunError(thread.run.error ?? undefined, thread.run.status)}
              </div>
            ) : null}
            {isBusy ? (
              <div className="flex justify-start">
                <div
                  data-testid="typing-indicator"
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className="flex items-center gap-1.5 rounded-[18px] border border-hairline bg-plate px-4 py-3"
                >
                  {flightText ? (
                    <p className="m-0 text-[13.5px] leading-5 text-mute">{flightText}</p>
                  ) : (
                    <>
                      <span className="sr-only">Working</span>
                      <span aria-hidden="true" className="flex items-center gap-1.5">
                        <span className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan" />
                        <span
                          className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan"
                          style={{ animationDelay: "150ms" }}
                        />
                        <span
                          className="ab-pulse inline-block h-2 w-2 rounded-full bg-tan"
                          style={{ animationDelay: "300ms" }}
                        />
                      </span>
                    </>
                  )}
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
            {/* File drop and paste land on the Message row, not a dedicated control. */}
            {/* biome-ignore lint/a11y/noStaticElementInteractions: composer drop/paste target */}
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
                      ? composerPlaceholder(active.name)
                      : "Create a bot to start"
                }
                className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-none rounded-[10px] border border-hairline bg-raised px-3 py-2.5 text-[15px] leading-[22px] text-paper disabled:cursor-not-allowed disabled:opacity-40"
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
          data-shell="hatch"
          data-hatch-open={hatchOpen ? "1" : "0"}
          data-phone-show={phoneTab === "desk" ? "1" : "0"}
          onWheel={(event) => {
            if (hatchOpen) event.stopPropagation();
          }}
          className={`flex h-full min-h-0 shrink-0 flex-col overflow-hidden bg-ink ${
            hatchPointerEvents(hatchOpen) === "none" ? "pointer-events-none" : "pointer-events-auto"
          } ${
            phoneShell
              ? "w-full max-w-none border-l-0"
              : hatchOpen
                ? "w-[360px] border-l border-hairline"
                : "w-0"
          }`}
        >
          {hatchOpen ? (
            <div
              className={`ab-scroll h-full overflow-y-auto px-4 py-3 ${
                phoneShell ? "w-full" : "w-[360px]"
              }`}
            >
              {panel === "plugins" ? (
                <PluginsPane
                  onClose={() => {
                    setPanel(null);
                    if (phoneShell) setPhoneTab(nextPhoneTab("close-desk"));
                  }}
                />
              ) : null}
              {panel === "models" ? (
                <ModelsPane
                  botId={active?.id}
                  credentials={modelState}
                  onChange={setModelState}
                  onClose={closeModels}
                  onApplied={() => {
                    const id = activeIdRef.current;
                    if (id) void refreshThread(id);
                  }}
                />
              ) : null}
              {panel === "create" ? (
                <CreateBotForm onCancel={closeCreate} onCreate={(input) => void createBot(input)} />
              ) : null}
              {panel === "settings" && active ? (
                <BotSettings
                  bot={active}
                  computer={computer ?? snapshot?.computer ?? null}
                  onClose={closeSettings}
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
                  onClose={() => {
                    setPanel(null);
                    if (phoneShell) setPhoneTab(nextPhoneTab("close-desk"));
                  }}
                  onSettings={() => {
                    panelAfterSettings.current = "computer";
                    setPanel("settings");
                  }}
                  onOpenFullscreen={() => void openOverlay("preview")}
                  onStart={() =>
                    void bootComputer({
                      takeControl: shouldTakeControl("start"),
                    })
                  }
                  onTakeControl={() => void openOverlay("button")}
                  onRelease={() => void releaseComputer()}
                  onRetryScreen={retryScreen}
                  onScreenFrameLoad={onScreenFrameLoad}
                  onLater={setLater}
                  memoryFocusFact={memoryFocusFact}
                />
              ) : null}
            </div>
          ) : null}
        </aside>

        {messageMenu ? (
          <MessageContextMenu
            position={messageMenu.position}
            url={messageMenu.url}
            canCopy={Boolean(messageCopyText(messageMenu.message))}
            onClose={() => setMessageMenu(null)}
            onCopy={async () => {
              const text = messageCopyText(messageMenu.message);
              if (!text) return false;
              const copied = await copyText(text);
              if (!copied) {
                errorKindRef.current = "action";
                setErrorKind("action");
                setError("Could not copy. Select the text instead.");
              }
              return copied;
            }}
            onCopyUrl={async () => {
              if (!messageMenu.url) return false;
              const copied = await copyText(messageMenu.url);
              if (!copied) {
                errorKindRef.current = "action";
                setErrorKind("action");
                setError("Could not copy URL. Select and copy the link instead.");
              }
              return copied;
            }}
            onOpenUrl={() => {
              if (messageMenu.url) {
                openOwnerBrowser(messageMenu.url);
              }
              setMessageMenu(null);
            }}
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
                setArchivedBots((list) => [
                  target,
                  ...list.filter((item) => item.id !== target.id),
                ]);
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
      </div>

      <nav data-testid="phone-nav" className="phone-nav" aria-label="Phone sections">
        <button
          type="button"
          data-testid="phone-tab-chats"
          aria-current={phoneTab === "chats" ? "page" : undefined}
          onClick={() => setPhoneTab(nextPhoneTab("open-chats"))}
        >
          Chats
        </button>
        <button
          type="button"
          data-testid="phone-tab-chat"
          aria-current={phoneTab === "chat" ? "page" : undefined}
          onClick={() => setPhoneTab(nextPhoneTab("open-chat"))}
        >
          Chat
        </button>
        <button
          type="button"
          data-testid="phone-tab-desk"
          aria-current={phoneTab === "desk" ? "page" : undefined}
          onClick={() => {
            setPhoneTab(nextPhoneTab("open-desk"));
            if (active) setPanel((current) => current || "computer");
          }}
        >
          Desktop
        </button>
      </nav>

      <ComputerOverlay
        booting={booting}
        open={computerOpen}
        bot={active}
        computer={computer ?? snapshot?.computer ?? null}
        screenUrl={screenUrl}
        screenError={screenError}
        screenEpoch={screenEpoch}
        overlayFrameRef={overlayFrameRef}
        onRelease={() => void releaseComputer()}
        onTakeControl={() => void bootComputer({ takeControl: true })}
        onClose={() => {
          setComputerOpen(false);
          if (phoneShell) setPhoneTab(nextPhoneTab("close-desk"));
        }}
        onRetry={retryScreen}
        onScreenFrameLoad={onScreenFrameLoad}
        onScreenError={(message) => setScreenError(message)}
        phone={phoneDesk}
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
        >
          <track kind="captions" label="No captions for this file" srcLang="en" />
        </video>
      ) : null}
      {kind === "audio" && url ? (
        <audio data-testid="attach-preview" src={url} controls className="h-8 max-w-[220px]">
          <track kind="captions" label="No captions for this file" srcLang="en" />
        </audio>
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
