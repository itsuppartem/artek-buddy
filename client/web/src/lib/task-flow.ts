type TaskStageSource = {
  status: string;
  unread: boolean;
  preview: string;
};

export type BotTaskStage = "decision" | "working" | "ready" | "recent";

export function botTaskStage(bot: TaskStageSource): BotTaskStage {
  const status = bot.status.toLocaleLowerCase();
  const preview = bot.preview.toLocaleLowerCase();
  const decisionWords = [
    "approval",
    "approve",
    "permission",
    "needs you",
    "needs your",
    "question",
    "asking",
  ];
  if (
    status === "waiting_input" ||
    status === "waiting_takeover" ||
    status === "needs_you" ||
    (bot.unread && decisionWords.some((word) => preview.includes(word)))
  ) {
    return "decision";
  }
  if (!["", "idle", "sleeping", "suspended", "done"].includes(status)) return "working";
  if (bot.unread) return "ready";
  return "recent";
}
