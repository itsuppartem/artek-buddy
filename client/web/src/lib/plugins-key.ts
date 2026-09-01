export type PluginsKeyStatus = {
  configured: boolean;
  lastFour: string | null;
};

export function nextPluginsFetchGen(live: number): number {
  return live + 1;
}

export function pluginsFetchIsCurrent(started: number, live: number): boolean {
  return started === live;
}

export function pluginsKeyMissingStatus(): PluginsKeyStatus {
  return { configured: false, lastFour: null };
}

export function pluginsHttpClearsSavedKey(status: number | undefined): boolean {
  return status === 409;
}
