const RAW_RUN_FAILED = /^run failed: run-[0-9a-f-]+$/i;

export const TURN_FAILED = "The turn failed.";

export function isRawRunFailed(text: string): boolean {
  return RAW_RUN_FAILED.test(text.trim()) || text.trim().startsWith("run failed: run-");
}

export function ownerRunError(error: string | undefined, status?: string): string {
  if (status === "cancelled") {
    const text = (error || "").trim();
    return text || "Stopped.";
  }
  const text = (error || "").trim();
  if (!text || isRawRunFailed(text)) return TURN_FAILED;
  return text;
}
