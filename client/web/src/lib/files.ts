import { ApiError, api } from "../api";

export class DownloadCancelled extends Error {
  constructor() {
    super("Save cancelled");
    this.name = "DownloadCancelled";
  }
}

export function formatBytes(size: number): string {
  const n = Number(size) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) {
    const kb = n / 1024;
    return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  }
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function requireSaved(saved: { ok?: boolean; path?: string } | null | undefined): { path: string } {
  if (saved?.ok && saved.path) {
    return { path: saved.path };
  }
  throw new Error("Could not download that file");
}

function rethrowSaveError(err: unknown): never {
  if (err instanceof ApiError && err.status === 409) {
    throw new DownloadCancelled();
  }
  throw err;
}

export async function downloadArtifact(artifactId: string, name: string): Promise<{ path: string }> {
  if (!artifactId) {
    throw new Error("Could not download that file");
  }
  try {
    return requireSaved(await api.local.saveArtifact({ artifactId, name }));
  } catch (err) {
    rethrowSaveError(err);
  }
}

export function artifactUrl(artifactId: string): string {
  return `/v1/artifacts/${encodeURIComponent(artifactId)}`;
}
