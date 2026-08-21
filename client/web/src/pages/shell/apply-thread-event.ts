import type { Dispatch, SetStateAction } from "react";
import { isComputerStatusEvent, reduceComputerStatus, reduceThreadSnapshot } from "../../lib/thread-events";
import type { ComputerStatus, ProductEvent, ThreadSnapshot } from "../../types";

export function applyThreadEvent(
  event: ProductEvent,
  setSnapshot: Dispatch<SetStateAction<ThreadSnapshot | null>>,
  setComputer: Dispatch<SetStateAction<ComputerStatus | null>>,
) {
  if (
    event.type === "thread.progress" ||
    event.type === "thread.message.created" ||
    event.type === "thread.message.updated" ||
    event.type === "thread.meta" ||
    event.type === "thread.subagent" ||
    event.type === "thread.computer" ||
    event.type === "bot.spawned" ||
    event.type === "agent.tool.called" ||
    event.type === "run.started" ||
    event.type === "run.waiting_input" ||
    event.type === "run.completed" ||
    event.type === "run.failed" ||
    event.type === "run.cancelled"
  ) {
    setSnapshot((prev) => reduceThreadSnapshot(prev, event));
  }
  if (isComputerStatusEvent(event)) {
    setComputer((prev) => reduceComputerStatus(prev, event));
  }
}
