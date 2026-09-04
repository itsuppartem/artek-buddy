type RoutableBot = {
  id: string;
  name: string;
  title: string;
  description: string;
  instructions: string;
  pinned: boolean;
};

type TaskStageSource = {
  status: string;
  unread: boolean;
  preview: string;
};

export type BotTaskStage = "decision" | "working" | "ready" | "recent";

const STOP_WORDS = new Set([
  "and",
  "for",
  "from",
  "help",
  "into",
  "me",
  "the",
  "this",
  "through",
  "with",
]);

function words(value: string): string[] {
  return value
    .toLocaleLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((word) => word.length >= 3 && !STOP_WORDS.has(word));
}

function wordStem(word: string): string {
  if (word.endsWith("ies") && word.length > 4) return `${word.slice(0, -3)}y`;
  if (word.endsWith("es") && word.length > 4) return word.slice(0, -2);
  if (word.endsWith("s") && word.length > 4) return word.slice(0, -1);
  return word;
}

function sameWord(left: string, right: string): boolean {
  const leftStem = wordStem(left);
  const rightStem = wordStem(right);
  if (leftStem === rightStem) return true;
  if (Math.min(leftStem.length, rightStem.length) < 4) return false;
  return leftStem.startsWith(rightStem) || rightStem.startsWith(leftStem);
}

function overlapScore(bot: RoutableBot, taskWords: string[]): number {
  const identityWords = words(`${bot.name} ${bot.title}`);
  const detailWords = words(`${bot.description} ${bot.instructions}`);
  return taskWords.reduce((score, taskWord) => {
    if (identityWords.some((word) => sameWord(word, taskWord))) return score + 3;
    if (detailWords.some((word) => sameWord(word, taskWord))) return score + 1;
    return score;
  }, 0);
}

export function suggestTaskBot<T extends RoutableBot>(bots: T[], task: string): T | undefined {
  if (!bots.length) return undefined;
  const taskWords = words(task);
  const ranked = bots
    .map((bot, index) => ({ bot, index, score: overlapScore(bot, taskWords) }))
    .sort((left, right) => right.score - left.score || left.index - right.index);
  if ((ranked[0]?.score ?? 0) >= 2) return ranked[0]?.bot;
  return bots.find((bot) => bot.pinned) ?? bots[0];
}

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
