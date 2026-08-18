import { camelize, snakify } from "./camel";
import type { LocalStatus, PairedDevice } from "./lib/pairing";
import type {
  Bot,
  ComputerStatus,
  MemoryDocument,
  ProductEvent,
  Routine,
  Subagent,
  ThreadMessagePage,
  ThreadSendResult,
  ThreadSnapshot,
} from "./types";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(snakify(body));
  }
  const response = await fetch(path, init);
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
    throw new Error(message);
  }
  return camelize<T>(parsed);
}

export const api = {
  local: {
    status() {
      return request<LocalStatus>("GET", "/local/status");
    },
    pair(input: { url?: string; pairingCode: string; name: string; platform?: string }) {
      return request<{ ok: boolean; device: PairedDevice; error?: string }>("POST", "/local/pair", input);
    },
    notify(input: { title: string; body: string; urgency: "low" | "normal" | "critical" }) {
      return request<{ ok: boolean }>("POST", "/local/notify", input).catch(() => ({ ok: false }));
    },
  },
  health() {
    return request<{ ok: boolean; agentId?: string; db?: boolean }>("GET", "/health");
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
      return request<{ ok: boolean }>("DELETE", `/v1/memory/${documentId}`);
    },
    exportMarkdown(botId: string) {
      return request<{ markdown: string }>(
        "GET",
        `/v1/memory/export?bot_id=${encodeURIComponent(botId)}`,
      ).then((data) => data.markdown ?? "");
    },
  },
  routines: {
    list(botId: string) {
      return request<{ routines: Routine[] }>("GET", `/v1/routines?bot_id=${encodeURIComponent(botId)}`).then(
        (data) => data.routines ?? [],
      );
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
      return request<{ ok: boolean }>("DELETE", `/v1/routines/${routineId}`);
    },
    testRun(routineId: string) {
      return request<{ routineId: string; taskId: string; runId: string; seq: number }>(
        "POST",
        `/v1/routines/${routineId}/test`,
      );
    },
  },
  me: {
    get() {
      return request<{
        userId: string;
        email: string;
        name: string;
        workspaceId: string;
        isDeploymentOwner: boolean;
        needsModel: boolean;
        defaultProvider?: string | null;
        defaultModel?: string | null;
        computerHost?: "docker" | "host" | null;
        canChooseHostComputer: boolean;
      }>("GET", "/v1/me");
    },
  },
  deployment: {
    get() {
      return request<{
        ownerUserId?: string | null;
        signupsEnabled: boolean;
        signupAllowlist: string[];
        hasDeploymentModelCredential: boolean;
        defaultProvider?: string | null;
        defaultModel?: string | null;
        computerHost?: "docker" | "host" | null;
        canChooseHostComputer: boolean;
      }>("GET", "/v1/deployment");
    },
    update(patch: {
      signupsEnabled?: boolean;
      signupAllowlist?: string[];
      computerHost?: "docker" | "host" | null;
    }) {
      return request<{
        ownerUserId?: string | null;
        signupsEnabled: boolean;
        signupAllowlist: string[];
        hasDeploymentModelCredential: boolean;
        defaultProvider?: string | null;
        defaultModel?: string | null;
        computerHost?: "docker" | "host" | null;
        canChooseHostComputer: boolean;
      }>("PATCH", "/v1/deployment", patch);
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
      return request<{ ok: boolean }>("POST", `/v1/bots/${botId}/archive`);
    },
    restore(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/bots/${botId}/restore`);
    },
    remove(botId: string, deleteMemories: boolean = false) {
      const query = deleteMemories ? "?delete_memories=true" : "";
      return request<{ ok: boolean }>("DELETE", `/v1/bots/${botId}${query}`);
    },
  },
  subagents: {
    list(botId: string) {
      return request<{ subagents: Subagent[] }>(
        "GET",
        `/v1/bots/${botId}/subagents`,
      ).then((data) => data.subagents ?? []);
    },
    stop(botId: string, subagentId: string) {
      return request<Subagent>("POST", `/v1/bots/${botId}/subagents/${subagentId}/stop`);
    },
    restart(botId: string, subagentId: string) {
      return request<Subagent>("POST", `/v1/bots/${botId}/subagents/${subagentId}/restart`);
    },
  },
  computer: {
    status(botId: string) {
      return request<ComputerStatus>("GET", `/v1/computer/${botId}`);
    },
    boot(botId: string) {
      return request<ComputerStatus>("POST", `/v1/computer/${botId}/boot`);
    },
    takeover(botId: string) {
      return request<{ leaseId: string; expiresAt: string }>("POST", `/v1/computer/${botId}/takeover`);
    },
    release(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/computer/${botId}/release`);
    },
    heartbeat(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/computer/${botId}/heartbeat`);
    },
    screenUrl(botId: string) {
      return request<{ url: string | null }>("GET", `/v1/computer/${botId}/screen`);
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
    send(botId: string, text: string, replyToId?: string | null) {
      return request<ThreadSendResult>("POST", `/v1/threads/${botId}/messages`, {
        text,
        replyToId: replyToId || undefined,
      });
    },
    stop(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/threads/${botId}/stop`);
    },
    followUp(botId: string, text: string) {
      return request<{ ok: boolean }>("POST", `/v1/threads/${botId}/follow-up`, { text });
    },
    markRead(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/threads/${botId}/read`);
    },
    markUnread(botId: string) {
      return request<{ ok: boolean }>("POST", `/v1/threads/${botId}/unread`);
    },
    async *subscribe(
      botId: string,
      after: string | null,
      signal: AbortSignal,
    ): AsyncGenerator<ProductEvent> {
      const query = after ? `?after=${encodeURIComponent(after)}` : "";
      const response = await fetch(`/v1/threads/${botId}/events${query}`, {
        headers: { Accept: "text/event-stream" },
        signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`subscribe ${response.status}`);
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
    },
  },
};

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
  return status === "queued" || status === "leased" || status === "running";
}
