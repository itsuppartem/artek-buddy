export function composerCanSend(draft: string, fileCount: number): boolean {
  return draft.trim().length > 0 || fileCount > 0;
}
