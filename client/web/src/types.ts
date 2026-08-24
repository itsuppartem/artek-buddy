import type { Camelize } from "./camel";
import type { components } from "./generated/openapi";

type Schema = components["schemas"];

export type ComputerMode = Schema["Bot"]["computer_mode"];
export type RunStatus = Schema["RunStatus"];
export type MemoryScope = Schema["MemoryScope"];

export type Bot = Camelize<Schema["Bot"]>;
export type ComputerStatus = Camelize<Schema["ComputerStatus"]>;
export type ComputerFileEntry = Camelize<Schema["ComputerFileEntry"]>;
export type ComputerFileList = Camelize<Schema["ComputerFileList"]>;
export type ComputerFileContent = Camelize<Schema["ComputerFileContent"]>;
export type ScreenUrlResult = Camelize<Schema["ScreenUrlResult"]>;
export type TakeoverResult = Camelize<Schema["TakeoverResult"]>;
export type Run = Camelize<Schema["Run"]>;
export type ThreadMessage = Camelize<Schema["ThreadMessage"]>;
export type MessageBlock = ThreadMessage["blocks"][number];
export type MessageReply = Camelize<Schema["MessageReplyRef"]>;
export type Subagent = Camelize<Schema["Subagent"]>;
export type ThreadSnapshot = Camelize<Schema["ThreadSnapshot"]>;
export type ThreadMessagePage = Camelize<Schema["ThreadMessagePage"]>;
export type MemoryDocument = Camelize<Schema["MemoryDocument"]>;
export type Routine = Camelize<Schema["Routine"]>;
export type ThreadSendResult = Camelize<Schema["ThreadSendResult"]>;
export type HealthResponse = Camelize<Schema["HealthResponse"]>;
export type Me = Camelize<Schema["Me"]>;
export type DeploymentSettings = Camelize<Schema["DeploymentSettings"]>;
export type ConsentJob = Camelize<Schema["ConsentJob"]>;
export type OkResponse = Camelize<Schema["OkResponse"]>;
export type TestRunResult = Camelize<Schema["TestRunResult"]>;
export type MarkdownExport = Camelize<Schema["MarkdownExport"]>;
export type ModelCredential = {
  id: string;
  provider: string;
  label: string;
  hasKey: boolean;
  isDefault: boolean;
  lastFour?: string | null;
  error?: string | null;
};
export type ModelCredentialList = {
  credentials: ModelCredential[];
  defaultProvider: string | null;
  defaultModel: string | null;
};
export type ModelInfo = { id: string; provider: string };
export type ModelListResponse = { models: ModelInfo[] };

export type ProductEvent = {
  id: string;
  workspaceId: string;
  threadId: string;
  botId: string;
  seq: number;
  type: string;
  createdAt: string;
  payload: Record<string, unknown>;
  runId?: string | null;
};

export type DesktopBridge = {
  platform: "linux" | "darwin" | "win32";
  window: {
    close: () => void;
    minimize: () => void;
    toggleMaximize: () => void;
  };
};

declare global {
  interface Window {
    artekDesktop?: DesktopBridge;
  }
}
