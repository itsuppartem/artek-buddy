import { useState } from "react";
import {
  artifactUrl,
  DownloadCancelled,
  downloadArtifact,
  formatBytes,
  startBrowserDownload,
  usesBrowserDownload,
} from "../../lib/files";
import { previewKind } from "../../lib/uploads";
import type { ThreadMessage } from "../../types";
import { Button } from "../../ui/button";

export type FileBlock = Extract<ThreadMessage["blocks"][number], { kind: "file" }>;

export function FileCard({ block }: { block: FileBlock }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const kind = previewKind(new File([], block.name, { type: block.mimeType || "" }));
  const preview = block.artifactId ? artifactUrl(block.artifactId) : "";

  async function download() {
    if (busy) return;
    setError("");
    setSaved("");
    if (usesBrowserDownload()) {
      try {
        startBrowserDownload(block.artifactId, block.name);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not download that file");
      }
      return;
    }
    setBusy(true);
    try {
      const result = await downloadArtifact(block.artifactId, block.name);
      setSaved(result.path);
    } catch (err) {
      if (err instanceof DownloadCancelled) return;
      setError(err instanceof Error ? err.message : "Could not download that file");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="file-card"
      className="min-w-0 max-w-[74%] rounded-[20px] border border-hairline bg-raised px-5 py-[17px]"
    >
      <div className="break-words [overflow-wrap:anywhere] text-[15.5px] font-medium leading-[1.4] text-paper">
        {block.name}
      </div>
      <div className="mt-1 text-[13px] text-mute">{formatBytes(block.size)}</div>
      {kind === "image" && preview ? (
        <img
          data-testid="file-preview"
          src={preview}
          alt={block.name}
          className="mt-3 max-h-64 w-full rounded-xl object-contain bg-ink"
        />
      ) : null}
      {kind === "video" && preview ? (
        <video
          data-testid="file-preview"
          src={preview}
          controls
          preload="metadata"
          className="mt-3 max-h-64 w-full rounded-xl"
        >
          <track kind="captions" label="No captions for this file" srcLang="en" />
        </video>
      ) : null}
      {kind === "audio" && preview ? (
        <audio data-testid="file-preview" src={preview} controls className="mt-3 w-full">
          <track kind="captions" label="No captions for this file" srcLang="en" />
        </audio>
      ) : null}
      {block.artifactId ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          data-testid="file-download"
          aria-label={`Download ${block.name}`}
          disabled={busy}
          onClick={() => void download()}
        >
          {busy ? "Choose where…" : "Download"}
        </Button>
      ) : null}
      {saved ? (
        <div
          data-testid="file-saved"
          className="mt-2 break-words [overflow-wrap:anywhere] text-[13px] text-sage"
        >
          Saved to {saved}
        </div>
      ) : null}
      {error ? <div className="mt-2 text-[13px] text-danger">{error}</div> : null}
    </div>
  );
}
