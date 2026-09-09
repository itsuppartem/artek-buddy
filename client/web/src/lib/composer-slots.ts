import { type ComposerHistory, createComposerHistory, resetComposerHistory } from "./composer-undo";
import type { PendingFile } from "./uploads";

export type ComposerSlot<TReply = unknown> = {
  draft: string;
  history: ComposerHistory;
  pendingFiles: PendingFile[];
  sending: boolean;
  replyTo: TReply | null;
};

export type ComposerSendResult = { ok: true } | { ok: false; draft: string; files: PendingFile[] };

export function emptyComposerSlot<TReply = unknown>(): ComposerSlot<TReply> {
  return {
    draft: "",
    history: createComposerHistory(""),
    pendingFiles: [],
    sending: false,
    replyTo: null,
  };
}

export function beginComposerSend<TReply>(slot: ComposerSlot<TReply>): ComposerSlot<TReply> {
  return {
    ...slot,
    draft: "",
    history: resetComposerHistory(""),
    pendingFiles: [],
    sending: true,
  };
}

export function finishComposerSend<TReply>(slot: ComposerSlot<TReply>): ComposerSlot<TReply> {
  return { ...slot, sending: false, replyTo: null };
}

export function failComposerSend<TReply>(
  slot: ComposerSlot<TReply>,
  draft: string,
  files: PendingFile[],
): ComposerSlot<TReply> {
  return {
    ...slot,
    draft,
    history: resetComposerHistory(draft),
    pendingFiles: files,
    sending: false,
  };
}

export function applyComposerSendResult<TReply>(args: {
  currentBotId: string | undefined;
  targetId: string;
  live: ComposerSlot<TReply>;
  parked: ComposerSlot<TReply> | undefined;
  result: ComposerSendResult;
}): { live: ComposerSlot<TReply>; parked: ComposerSlot<TReply> | undefined } {
  const onTarget = args.currentBotId === args.targetId;
  const base = onTarget ? args.live : (args.parked ?? emptyComposerSlot<TReply>());
  const next = args.result.ok
    ? finishComposerSend(base)
    : failComposerSend(base, args.result.draft, args.result.files);
  if (onTarget) return { live: next, parked: args.parked };
  return { live: args.live, parked: next };
}
