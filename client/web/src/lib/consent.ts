import { ApiError, api } from "../api";
import type { ProductEvent } from "../types";
import { type PageSurface, pageSurface } from "./web-notify";

const HOST_OWNER_CUT = "This-PC files need the Linux app, not the phone browser.";

export function ownerJobHint(block: {
  text: string;
  detail?: string | null;
}): { kind: string; value: string } | null {
  const detail = (block.detail || "").trim();
  const match = /^(owner_read|owner_write|owner_list|owner_exec):\s*([\s\S]+)$/i.exec(detail);
  if (match) {
    const kind = match[1].toLowerCase();
    const value = kind === "owner_exec" ? match[2].split("\n")[0].trim() : match[2].trim();
    return value ? { kind, value } : null;
  }
  const read = /^Read (.+) from your computer\?$/i.exec(block.text.trim());
  if (read?.[1]) return { kind: "owner_read", value: read[1].trim() };
  const write = /^Write (.+) on your computer\?$/i.exec(block.text.trim());
  if (write?.[1]) return { kind: "owner_write", value: write[1].trim() };
  const list = /^List (.+) on your computer\?$/i.exec(block.text.trim());
  if (list?.[1]) return { kind: "owner_list", value: list[1].trim() };
  return null;
}

export function ownerReadPath(block: { text: string; detail?: string | null }): string | null {
  const hint = ownerJobHint(block);
  return hint?.kind === "owner_read" ? hint.value : null;
}

export function isAutoOwnerJob(event: ProductEvent): { consentId: string } | null {
  if (event.type !== "run.waiting_input") return null;
  const auto = event.payload.auto === true;
  const consentId = typeof event.payload.consentId === "string" ? event.payload.consentId : "";
  const action = typeof event.payload.actionClass === "string" ? event.payload.actionClass : "";
  if (!auto || !consentId || !action.startsWith("owner_")) return null;
  return { consentId };
}

export const isAutoOwnerFile = isAutoOwnerJob;

export function shouldAutoFulfillOwnerJob(surface: PageSurface = pageSurface()): boolean {
  return surface !== "host";
}

export function pendingOwnerJobIds(snapshot: {
  pendingAutoConsentId?: string | null;
  pendingAutoConsentIds?: (string | null)[] | null;
}): string[] {
  const ids = [...(snapshot.pendingAutoConsentIds || []), snapshot.pendingAutoConsentId];
  return [...new Set(ids.filter((value): value is string => Boolean(value)))];
}

export async function reportOwnerJobError(
  consentId: string,
  error: unknown,
  claim?: string,
): Promise<void> {
  const message = error instanceof Error ? error.message : "Could not run that on this computer";
  try {
    await api.consents.uploadResult(consentId, { ok: false, error: message, claim });
  } catch {
    /* the card answer still has to reach the host */
  }
}

export async function completeOwnerConsent(consentId: string, decision: string): Promise<void> {
  const allow =
    decision === "once" ||
    decision === "always" ||
    decision === "Allow once" ||
    decision === "Always";
  if (pageSurface() === "host" && allow) {
    try {
      const job = await api.consents.get(consentId);
      if (String(job.actionClass || "").startsWith("owner_")) {
        await reportOwnerJobError(consentId, new Error(HOST_OWNER_CUT));
        await api.consents.answer(consentId, decision);
        return;
      }
    } catch {
      /* browse and page cards still answer below */
    }
  }
  if (allow) {
    try {
      await fulfillOwnerJob(consentId);
    } catch (err) {
      await api.consents.answer(consentId, decision);
      throw err;
    }
  }
  await api.consents.answer(consentId, decision);
}

export async function fulfillOwnerJob(consentId: string): Promise<void> {
  let job: Awaited<ReturnType<typeof api.consents.get>>;
  try {
    job = await api.consents.get(consentId);
  } catch (error) {
    await reportOwnerJobError(consentId, error);
    throw error;
  }
  const action = job.actionClass;
  const kind = job.kind || "";
  let claim: string | undefined;
  if (action.startsWith("owner_")) {
    try {
      const acknowledged = await api.consents.ack(consentId);
      claim = acknowledged.claim || undefined;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) return;
      await reportOwnerJobError(consentId, error);
      throw error;
    }
  }
  try {
    const listHint = ownerJobHint({
      text: job.summary || "",
      detail: job.path ? `owner_list: ${job.path}` : "",
    });
    if (
      action === "owner_read" &&
      (kind === "list" || listHint?.kind === "owner_list" || /^List /i.test(job.summary || ""))
    ) {
      const listed = await api.local.ownerList(job.path || listHint?.value || "~");
      await api.consents.uploadResult(consentId, {
        ok: true,
        path: listed.path,
        entries: listed.entries,
        claim,
      });
      return;
    }
    if (action === "owner_read") {
      const path =
        job.path ||
        ownerReadPath({ text: job.summary || "", detail: `owner_read: ${job.path || ""}` });
      if (!path) throw new Error("missing path");
      const file = await api.local.ownerRead(path);
      await api.consents.uploadFile(consentId, {
        name: file.name,
        text: file.text,
        contentBase64: file.contentBase64,
        claim,
      });
      return;
    }
    if (action === "owner_write") {
      if (!job.path) throw new Error("missing path");
      const written = await api.local.ownerWrite({
        path: job.path,
        text: job.text ?? undefined,
        contentBase64: job.contentBase64 ?? undefined,
      });
      await api.consents.uploadResult(consentId, {
        ok: true,
        path: written.path,
        bytes: written.bytes,
        claim,
      });
      return;
    }
    if (action === "owner_exec") {
      if (!job.command) throw new Error("missing command");
      const ran = await api.local.ownerExec({ command: job.command, cwd: job.cwd || "~" });
      await api.consents.uploadResult(consentId, {
        ok: ran.ok,
        stdout: ran.stdout,
        stderr: ran.stderr,
        exitCode: ran.exitCode,
        error: ran.error,
        claim,
      });
      return;
    }
  } catch (error) {
    await reportOwnerJobError(consentId, error, claim);
    throw error;
  }
}

export async function deliverOwnerFile(consentId: string, path: string): Promise<void> {
  const file = await api.local.ownerRead(path);
  await api.consents.uploadFile(consentId, {
    name: file.name,
    text: file.text,
    contentBase64: file.contentBase64,
  });
}
