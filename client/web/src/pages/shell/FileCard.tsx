import { useState } from "react";
import { artifactUrl, DownloadCancelled, downloadArtifact, formatBytes } from "../../lib/files";
import { previewKind } from "../../lib/uploads";
import type { ThreadMessage } from "../../types";

export type FileBlock = Extract<ThreadMessage["blocks"][number], { kind: "file" }>;

export function FileCard({ block }: { block: FileBlock }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const kind = previewKind(new File([], block.name, { type: block.mimeType || "" }));
  const preview = block.artifactId ? artifactUrl(block.artifactId) : "";

  async function download() {
    if (busy) return;
    setBusy(true);
    setError("");
    setSaved("");
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
      className="min-w-0 max-w-[74%] rounded-[20px] border border-[#242428] bg-[#141417] px-5 py-[17px]"
    >
      <div className="break-words [overflow-wrap:anywhere] text-[15.5px] font-medium leading-[1.4] text-[#ECECEE]">
        {block.name}
      </div>
      <div className="mt-1 text-[13px] text-[#85858A]">{formatBytes(block.size)}</div>
      {kind === "image" && preview ? (
        <img
          data-testid="file-preview"
          src={preview}
          alt={block.name}
          className="mt-3 max-h-64 w-full rounded-xl object-contain bg-[#0D0D0E]"
        />
      ) : null}
      {kind === "video" && preview ? (
        <video
          data-testid="file-preview"
          src={preview}
          controls
          preload="metadata"
          className="mt-3 max-h-64 w-full rounded-xl"
        />
      ) : null}
      {kind === "audio" && preview ? (
        <audio data-testid="file-preview" src={preview} controls className="mt-3 w-full" />
      ) : null}
      <button
        type="button"
        className="mt-3 rounded-full bg-[#1B1B1E] px-3.5 py-1.5 text-[13.5px] text-[#C9C9CE] hover:bg-[#242428] disabled:opacity-60"
        disabled={busy}
        onClick={() => void download()}
      >
        {busy ? "Choose where…" : "Download"}
      </button>
      {saved ? (
        <div
          data-testid="file-saved"
          className="mt-2 break-words [overflow-wrap:anywhere] text-[13px] text-[#4ECB71]"
        >
          Saved to {saved}
        </div>
      ) : null}
      {error ? <div className="mt-2 text-[13px] text-[#E65707]">{error}</div> : null}
    </div>
  );
}
