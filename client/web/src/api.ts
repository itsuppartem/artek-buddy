import { camelize, snakify } from "./camel";
import type { LocalStatus, PairedDevice } from "./lib/pairing";
import type {
  BeginConnectionResult,
  Bot,
  ComputerFileContent,
  ComputerFileList,
  ComputerStatus,
  Connection,
  ConnectionCatalog,
  ConnectionKeyStatus,
  ConsentJob,
  DeploymentSettings,
  HealthResponse,
  MarkdownExport,
  Me,
  MemoryDocument,
  ModelCredential,
  ModelCredentialList,
  ModelListResponse,
  OkResponse,
  ProductEvent,
  Routine,
  ScreenUrlResult,
  SkillBook,
  Subagent,
  TakeoverResult,
  TestRunResult,
  ThreadMessagePage,
  ThreadSendResult,
  ThreadSnapshot,
} from "./types";

const REQUEST_TIMEOUT_MS = 30_000;

let localNonce = "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly retryable = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ShellErrorKind = "host" | "auth" | "action";

export function classifyError(err: unknown): { message: string; kind: ShellErrorKind } {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) {
      return { message: err.message, kind: "auth" };
    }
    if (err.retryable || err.status == null) {
      return { message: err.message, kind: "host" };
    }
    return { message: err.message, kind: "action" };
  }
  if (err instanceof Error && err.message) {
    return { message: err.message, kind: "action" };
  }
  return { message: "Something went wrong", kind: "action" };
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  const init: RequestInit = { method, headers, signal: controller.signal };
  const localMutating = path.startsWith("/local/") && method !== "GET";
  if (localMutating) {
    headers["Content-Type"] = "application/json";
    if (localNonce) {
      headers["X-Artek-Local-Nonce"] = localNonce;
    }
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(snakify(body));
  } else if (localMutating) {
    init.body = "{}";
  }
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(
        "The host did not respond in time. Check the connection and try again.",
        undefined,
        true,
      );
    }
    throw new ApiError(
      "Could not reach the host. Check Tailscale or the host address, then try again.",
      undefined,
      true,
    );
  } finally {
    globalThis.clearTimeout(timeout);
  }
  const raw = await response.text();
  let parsed: unknown = {};
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = raw;
    }
  }
  if (!response.ok) {
    const detail =
      typeof parsed === "object" && parsed && "detail" in parsed
        ? (parsed as { detail: unknown }).detail
        : typeof parsed === "object" && parsed && "error" in parsed
          ? (parsed as { error: unknown }).error
          : parsed;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: unknown }).message)
          : `${response.status} ${path}`;
    if ((response.status === 401 || response.status === 403) && path.startsWith("/v1/")) {
      throw new ApiError(
        "This computer is no longer authorized. Pair it again to continue.",
        response.status,
      );
    }
    throw new ApiError(message, response.status, response.status >= 500);
  }
  return camelize<T>(parsed);
}

export const api = {
  local: {
    status() {
      return request<LocalStatus>("GET", "/local/status").then((status) => {
        if (status.nonce) {
          localNonce = status.nonce;
        }
        return status;
      });
    },
    pair(input: { url?: string; pairingCode: string; name: string; platform?: string }) {
      return request<{ ok: boolean; device: PairedDevice; error?: string }>(
        "POST",
        "/local/pair",
        input,
      );
    },
    unpair() {
      return request<{ ok: boolean; paired?: boolean }>("POST", "/local/unpair");
    },
    notify(input: {
      title: string;
      body: string;
      urgency: "low" | "normal" | "critical";
      tag?: string;
    }) {
      return request<{ ok: boolean }>("POST", "/local/notify", input).catch(() => ({ ok: false }));
    },
    dismissNotify(tag: string) {
      return request<{ ok: boolean }>("POST", "/local/notify-dismiss", { tag }).catch(() => ({
        ok: false,
      }));
    },
    ownerRead(path: string) {
      return request<{
        ok: boolean;
        name: string;
        bytes: number;
        text?: string;
        contentBase64: string;
      }>("POST", "/local/owner-read", { path });
    },
    ownerWrite(input: { path: string; text?: string; contentBase64?: string }) {
      return request<{ ok: boolean; path: string; name: string; bytes: number }>(
        "POST",
        "/local/owner-write",
        input,
      );
    },
    ownerList(path: string) {
      return request<{
        ok: boolean;
        path: string;
        entries: { name: string; kind: string; size?: number | null }[];
      }>("POST", "/local/owner-list", { path });
    },
    ownerExec(input: { command: string; cwd?: string }) {
      return request<{
        ok: boolean;
        stdout: string;
        stderr: string;
        exitCode: number;
        error?: string;
      }>("POST", "/local/owner-exec", input);
    },
    saveArtifact(input: { artifactId: string; name: string }) {
      return request<{ ok: boolean; path: string; name: string; bytes: number }>(
        "POST",
        "/local/save-artifact",
        input,
        10 * 60 * 1000,
      );
    },
    saveHomeFile(input: { botId: string; path: string; name: string }) {
      return request<{ ok: boolean; path: string; name: string; bytes: number }>(
        "POST",
        "/local/save-home-file",
        input,
        10 * 60 * 1000,
      );
    },
    attachFiles(paths: string[]) {
      return request<{
        ok: boolean;
        files: { name: string; type: string; bytes: number; contentBase64: string }[];
      }>("POST", "/local/attach-files", { paths });
    },
  },
  consents: {
    get(consentId: string) {
      return request<ConsentJob>("GET", `/v1/consents/${encodeURIComponent(consentId)}`);
    },
    ack(consentId: string) {
      return request<{ ok: boolean; claim?: string | null }>(
        "POST",
        `/v1/consents/${encodeURIComponent(consentId)}/ack`,
        { claimCapable: true },
      );
    },
    answer(consentId: string, decision: string) {
      return request<OkResponse>("POST", `/v1/consents/${encodeURIComponent(consentId)}`, {
        decision,
      });
    },
    uploadFile(
      consentId: string,
      input: { name: string; text?: string; contentBase64?: string; claim?: string },
    ) {
      return request<OkResponse>(
        "POST",
        `/v1/consents/${encodeURIComponent(consentId)}/file`,
        input,
      );
    },
    uploadResult(
      consentId: string,
      input: {
        ok?: boolean;
        name?: string;
        text?: string;
        contentBase64?: string;
        stdout?: string;
        stderr?: string;
        exitCode?: number;
        path?: string;
        bytes?: number;
        entries?: unknown[];
        error?: string;
        claim?: string;
      },
    ) {
      return request<OkResponse>(
        "POST",
        `/v1/consents/${encodeURIComponent(consentId)}/result`,
        input,
      );
    },
  },
  health() {
    return request<HealthResponse>("GET", "/health");
  },
  memory: {
    list(botId: string) {
      return request<{ documents: MemoryDocument[] }>(
        "GET",
        `/v1/memory?bot_id=${encodeURIComponent(botId)}`,
      ).then((data) => data.documents ?? []);
    },
    create(input: { scope: "bot" | "user"; botId?: string; path?: string; content: string }) {
      return request<MemoryDocument>("POST", "/v1/memory", input);
    },
    update(documentId: string, content: string) {
      return request<MemoryDocument>("PATCH", `/v1/memory/${documentId}`, { content });
    },
    remove(documentId: string) {
      return request<OkResponse>("DELETE", `/v1/memory/${documentId}`);
    },
    exportMarkdown(botId: string) {
      return request<MarkdownExport>(
        "GET",
        `/v1/memory/export?bot_id=${encodeURIComponent(botId)}`,
      ).then((data) => data.markdown ?? "");
    },
  },
  routines: {
    list(botId: string) {
      return request<{ routines: Routine[] }>(
        "GET",
        `/v1/routines?bot_id=${encodeURIComponent(botId)}`,
      ).then((data) => data.routines ?? []);
    },
    create(input: {
      botId: string;
      name: string;
      prompt: string;
      cron: string;
      timezone?: string;
      notify?: boolean;
      active?: boolean;
    }) {
      return request<Routine>("POST", "/v1/routines", input);
    },
    update(
      routineId: string,
      input: Partial<{
        name: string;
        prompt: string;
        cron: string;
        timezone: string;
        notify: boolean;
        active: boolean;
      }>,
    ) {
      return request<Routine>("PATCH", `/v1/routines/${routineId}`, input);
    },
    remove(routineId: string) {
      return request<OkResponse>("DELETE", `/v1/routines/${routineId}`);
    },
    testRun(routineId: string) {
      return request<TestRunResult>("POST", `/v1/routines/${routineId}/test`);
    },
  },
  me: {
    get() {
      return request<Me>("GET", "/v1/me");
    },
  },
  deployment: {
    get() {
      return request<DeploymentSettings>("GET", "/v1/deployment");
    },
    update(patch: {
      signupsEnabled?: boolean;
      signupAllowlist?: string[];
      computerHost?: "docker" | "host" | null;
    }) {
      return request<DeploymentSettings>("PATCH", "/v1/deployment", patch);
    },
  },
  bots: {
    list() {
      return request<{ bots: Bot[] }>("GET", "/v1/bots").then((data) => data.bots ?? []);
    },
    listArchived() {
      return request<{ bots: Bot[] }>("GET", "/v1/bots/archived").then((data) => data.bots ?? []);
    },
    get(botId: string) {
      return request<Bot>("GET", `/v1/bots/${botId}`);
    },
    create(input: {
      name: string;
      title?: string;
      description?: string;
      instructions?: string;
      computerMode?: "team" | "dedicated";
    }) {
      return request<Bot>("POST", "/v1/bots", input);
    },
    duplicate(botId: string) {
      return request<Bot>("POST", `/v1/bots/${botId}/duplicate`);
    },
    update(
      botId: string,
      patch: Partial<{
        name: string;
        title: string;
        description: string;
        instructions: string;
        color: string;
        pinned: boolean;
        notifyOnFinish: boolean;
        unread: boolean;
        computerMode: "team" | "dedicated";
      }>,
    ) {
      return request<Bot>("PATCH", `/v1/bots/${botId}`, patch);
    },
    archive(botId: string) {
      return request<OkResponse>("POST", `/v1/bots/${botId}/archive`);
    },
    restore(botId: string) {
      return request<OkResponse>("POST", `/v1/bots/${botId}/restore`);
    },
    remove(botId: string, deleteMemories: boolean = false) {
      const query = deleteMemories ? "?delete_memories=true" : "";
      return request<OkResponse>("DELETE", `/v1/bots/${botId}${query}`);
    },
  },
  subagents: {
    list(botId: string) {
      return request<{ subagents: Subagent[] }>("GET", `/v1/bots/${botId}/subagents`).then(
        (data) => data.subagents ?? [],
      );
    },
    stop(botId: string, subagentId: string) {
      return request<Subagent>("POST", `/v1/bots/${botId}/subagents/${subagentId}/stop`);
    },
    restart(botId: string, subagentId: string) {
      return request<Subagent>("POST", `/v1/bots/${botId}/subagents/${subagentId}/restart`);
    },
  },
  books: {
    list(botId: string) {
      return request<{ books: SkillBook[] }>("GET", `/v1/bots/${botId}/books`);
    },
  },
  connections: {
    status() {
      return request<ConnectionKeyStatus>("GET", "/v1/connections/status");
    },
    setKey(apiKey: string) {
      return request<ConnectionKeyStatus>("POST", "/v1/connections/key", { apiKey });
    },
    clearKey() {
      return request<OkResponse>("DELETE", "/v1/connections/key");
    },
    catalog(q = "") {
      const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
      return request<ConnectionCatalog>("GET", `/v1/connections/catalog${query}`);
    },
    list() {
      return request<{ connections: Connection[] }>("GET", "/v1/connections");
    },
    begin(provider: string, redirectUrl: string) {
      return request<BeginConnectionResult>("POST", "/v1/connections", {
        provider,
        redirectUrl,
      });
    },
    complete(connectionId: string) {
      return request<Connection>("POST", `/v1/connections/${connectionId}/complete`);
    },
    revoke(connectionId: string) {
      return request<OkResponse>("POST", `/v1/connections/${connectionId}/revoke`);
    },
  },
  models: {
    credentials() {
      return request<ModelCredentialList>("GET", "/v1/models/credentials");
    },
    list() {
      return request<ModelListResponse>("GET", "/v1/models");
    },
    connect(provider: string, apiKey?: string) {
      return request<ModelCredential>("POST", "/v1/models/credentials", {
        provider,
        apiKey,
      });
    },
    forget(provider: string) {
      return request<OkResponse>("DELETE", `/v1/models/credentials/${provider}`);
    },
    setDefault(provider: string, model: string, effort?: string, fast?: boolean, botId?: string) {
      return request<OkResponse>("POST", "/v1/models/default", {
        provider,
        model,
        effort,
        fast,
        botId,
      });
    },
  },
  computer: {
    status(botId: string) {
      return request<ComputerStatus>("GET", `/v1/computer/${botId}`);
    },
    boot(botId: string) {
      return request<ComputerStatus>("POST", `/v1/computer/${botId}/boot`);
    },
    stop(botId: string) {
      return request<ComputerStatus>("POST", `/v1/computer/${botId}/stop`);
    },
    restart(botId: string) {
      return request<ComputerStatus>("POST", `/v1/computer/${botId}/restart`);
    },
    reset(botId: string) {
      return request<ComputerStatus>("POST", `/v1/computer/${botId}/reset`);
    },
    takeover(botId: string) {
      return request<TakeoverResult>("POST", `/v1/computer/${botId}/takeover`);
    },
    release(botId: string) {
      return request<OkResponse>("POST", `/v1/computer/${botId}/release`);
    },
    input(botId: string, body: { kind: string; payload: Record<string, unknown> }) {
      return request<OkResponse>("POST", `/v1/computer/${botId}/input`, body);
    },
    heartbeat(botId: string) {
      return request<OkResponse>("POST", `/v1/computer/${botId}/heartbeat`);
    },
    screenUrl(botId: string) {
      return request<ScreenUrlResult>("GET", `/v1/computer/${botId}/screen`);
    },
    files(botId: string, path = "", hidden = false) {
      const query = new URLSearchParams();
      if (path) query.set("path", path);
      if (hidden) query.set("hidden", "true");
      const suffix = query.toString() ? `?${query}` : "";
      return request<ComputerFileList>("GET", `/v1/computer/${botId}/files${suffix}`);
    },
    readFile(botId: string, path: string) {
      return request<ComputerFileContent>(
        "GET",
        `/v1/computer/${botId}/files/read?path=${encodeURIComponent(path)}`,
      );
    },
    fileUrl(botId: string, path: string) {
      return `/v1/computer/${botId}/files/raw?path=${encodeURIComponent(path)}`;
    },
  },
  threads: {
    get(botId: string) {
      return request<ThreadSnapshot>("GET", `/v1/threads/${botId}`);
    },
    messages(botId: string, before?: number | null) {
      const query = before == null ? "" : `?before=${before}`;
      return request<ThreadMessagePage>("GET", `/v1/threads/${botId}/messages${query}`);
    },
    send(
      botId: string,
      text: string,
      replyToId?: string | null,
      attachments?: { name: string; contentBase64: string; mimeType?: string }[],
    ) {
      return request<ThreadSendResult>(
        "POST",
        `/v1/threads/${botId}/messages`,
        {
          text,
          replyToId: replyToId || undefined,
          attachments: attachments?.length
            ? attachments.map((item) => ({
                name: item.name,
                contentBase64: item.contentBase64,
                mimeType: item.mimeType,
              }))
            : undefined,
        },
        attachments?.length ? 120_000 : REQUEST_TIMEOUT_MS,
      );
    },
    stop(botId: string) {
      return request<OkResponse>("POST", `/v1/threads/${botId}/stop`);
    },
    followUp(botId: string, text: string) {
      return request<OkResponse>("POST", `/v1/threads/${botId}/follow-up`, { text });
    },
    answer(botId: string, runId: string, messageId: string, answer: string) {
      return request<OkResponse>("POST", `/v1/threads/${botId}/answer`, {
        runId,
        messageId,
        answer,
      });
    },
    markRead(botId: string) {
      return request<OkResponse>("POST", `/v1/threads/${botId}/read`);
    },
    markUnread(botId: string) {
      return request<OkResponse>("POST", `/v1/threads/${botId}/unread`);
    },
    async *subscribe(
      botId: string,
      after: string | null,
      signal: AbortSignal,
    ): AsyncGenerator<ProductEvent> {
      const query = after ? `?after=${encodeURIComponent(after)}` : "";
      yield* readSse(`/v1/threads/${botId}/events${query}`, signal);
    },
  },
  events: {
    async *subscribe(signal: AbortSignal): AsyncGenerator<ProductEvent> {
      yield* readSse("/v1/events", signal);
    },
  },
};

async function* readSse(path: string, signal: AbortSignal): AsyncGenerator<ProductEvent> {
  const response = await fetch(path, {
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!response.ok || !response.body) {
    if (response.status === 401 || response.status === 403) {
      throw new ApiError(
        "This computer is no longer authorized. Pair it again to continue.",
        response.status,
      );
    }
    throw new ApiError(
      "Live updates stopped. Check the host connection and try again.",
      response.status || undefined,
      true,
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    while (true) {
      const index = buffer.indexOf("\n");
      if (index < 0) break;
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);
      if (line === "") {
        if (dataLines.length) {
          const raw = dataLines.join("\n");
          dataLines = [];
          try {
            const parsed = camelize<ProductEvent>(JSON.parse(raw));
            if (eventName && eventName !== "message") parsed.type = eventName;
            yield parsed;
          } catch {
            // ignore a broken frame and keep the stream
          }
        }
        eventName = "message";
        continue;
      }
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
  }
}

export function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export function isActive(status: string | undefined): boolean {
  return (
    status === "queued" ||
    status === "leased" ||
    status === "running" ||
    status === "waiting_input" ||
    status === "waiting_takeover"
  );
}

export function isParkedTakeover(status: string | undefined): boolean {
  return status === "waiting_takeover";
}

export function isLiveTurn(status: string | undefined): boolean {
  return isActive(status) && !isParkedTakeover(status);
}
