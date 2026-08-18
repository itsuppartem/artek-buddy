import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export function clientLogPath(): string {
  const home = process.env.ARTEK_E2E_HOME || homedir();
  return join(home, ".config", "artek-buddy", "client.log");
}

export function readClientLogTail(lines = 20): string {
  try {
    const raw = readFileSync(clientLogPath(), "utf8").trim().split("\n");
    return raw.slice(-lines).join("\n");
  } catch {
    return "(no client.log)";
  }
}
