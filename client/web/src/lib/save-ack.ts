import { useCallback, useEffect, useRef, useState } from "react";

export const SAVE_ACK_MS = 1500;

export type SaveAckState = "idle" | "saving" | "saved";

export function saveButtonLabel(state: SaveAckState): string {
  if (state === "saving") return "Saving…";
  if (state === "saved") return "Saved";
  return "Save";
}

export function useSaveAck() {
  const [state, setState] = useState<SaveAckState>("idle");
  const [error, setError] = useState("");
  const timer = useRef(0);

  const cancel = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = 0;
    setState("idle");
    setError("");
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const run = useCallback(async (task: () => Promise<void>, afterSaved?: () => void) => {
    setError("");
    setState("saving");
    try {
      await task();
      setState("saved");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => {
        setState("idle");
        afterSaved?.();
      }, SAVE_ACK_MS);
    } catch (err) {
      setState("idle");
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }, []);

  return { state, error, label: saveButtonLabel(state), run, cancel };
}
