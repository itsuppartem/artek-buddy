const PATH = /^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;

export function isMemoryPath(value: string): boolean {
  const path = value.trim();
  return Boolean(path) && !path.includes("..") && PATH.test(path);
}

export function formatMemoryExport(documents: { path: string; content: string }[]): string {
  return documents
    .map((document) => `# ${document.path}\n\n${document.content}`.trimEnd())
    .join("\n\n");
}
