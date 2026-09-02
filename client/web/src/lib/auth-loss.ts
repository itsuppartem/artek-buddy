import { classifyError } from "../api";

export function workspaceEventsAuthLoss(err: unknown): "repair" | "retry" {
  return classifyError(err).kind === "auth" ? "repair" : "retry";
}
