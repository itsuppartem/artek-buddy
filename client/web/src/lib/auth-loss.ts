import { classifyError, type ShellErrorKind } from "../api";

export function workspaceEventsAuthLoss(err: unknown): "repair" | "retry" {
  return classifyError(err).kind === "auth" ? "repair" : "retry";
}

export function healthOkClearsError(kind: ShellErrorKind | null): boolean {
  return kind === "host";
}
