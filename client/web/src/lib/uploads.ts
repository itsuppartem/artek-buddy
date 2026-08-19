export const MAX_UPLOAD_FILES = 10;
export const MAX_UPLOAD_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_UPLOAD_TOTAL_BYTES = 50 * 1024 * 1024;

export type PendingFile = {
  id: string;
  file: File;
};

export type PreviewKind = "image" | "video" | "audio" | "file";

export function isMediaClipboardType(type: string): boolean {
  const value = (type || "").toLowerCase();
  return value.startsWith("image/") || value.startsWith("video/") || value.startsWith("audio/");
}

export function previewKind(file: File): PreviewKind {
  const type = (file.type || "").toLowerCase();
  if (type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name || "")) return "image";
  if (type.startsWith("video/") || /\.(mp4|webm|mov|mkv)$/i.test(file.name || "")) return "video";
  if (type.startsWith("audio/") || /\.(mp3|wav|ogg|m4a|flac)$/i.test(file.name || "")) return "audio";
  return "file";
}

function mimeExtension(type: string): string {
  const known: Record<string, string> = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
  };
  if (known[type]) return known[type];
  const subtype = type.split("/")[1] || "";
  return /^[a-z0-9]+$/i.test(subtype) ? subtype : "bin";
}

function pasteStem(kind: PreviewKind): string {
  if (kind === "image") return "screenshot";
  if (kind === "video") return "clip";
  if (kind === "audio") return "audio";
  return "paste";
}

export function nameClipboardFile(file: File, index: number): File {
  const name = (file.name || "").trim();
  if (name && name !== "blob") return file;
  const type = file.type || (previewKind(file) === "image" ? "image/png" : file.type);
  const kind = previewKind(new File([file], name, { type }));
  return new File([file], `${pasteStem(kind)}-${index + 1}.${mimeExtension(type || "image/png")}`, {
    type: type || "image/png",
    lastModified: file.lastModified,
  });
}

function clipboardItems(data: DataTransfer): DataTransferItem[] {
  return Array.from(data.items || []);
}

function clipboardText(data: DataTransfer, type: string): string {
  if (typeof data.getData !== "function") return "";
  try {
    return String(data.getData(type) || "");
  } catch {
    return "";
  }
}

export function normalizeClipboardPath(raw: string): string | null {
  let text = (raw || "").trim();
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    text = text.slice(1, -1).trim();
  }
  if (!text || text.startsWith("#")) return null;
  const command = text.toLowerCase();
  if (command === "copy" || command === "cut" || command === "link") return null;
  if (text.startsWith("file:")) {
    try {
      const url = new URL(text);
      if (url.protocol !== "file:") return null;
      if (url.hostname && url.hostname !== "localhost") return null;
      const path = decodeURIComponent(url.pathname || "");
      return path.startsWith("/") ? path : null;
    } catch {
      return null;
    }
  }
  if (text === "~" || text.startsWith("~/") || (text.startsWith("/") && text.length > 1)) return text;
  return null;
}

function pathsFromClipboardText(text: string): string[] {
  const lines = text
    .replace(/\0/g, "\n")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return [];
  const paths: string[] = [];
  for (const line of lines) {
    const command = line.toLowerCase();
    if (command === "copy" || command === "cut" || command === "link" || line.startsWith("#")) {
      continue;
    }
    const path = normalizeClipboardPath(line);
    if (path == null) return [];
    paths.push(path);
  }
  return [...new Set(paths)];
}

export function transferFilePaths(data: DataTransfer | null | undefined): string[] {
  if (!data) return [];
  const typed = ["text/uri-list", "x-special/gnome-copied-files", "text/x-moz-url"].map((type) =>
    clipboardText(data, type),
  );
  for (const text of typed) {
    const paths = pathsFromClipboardText(text);
    if (paths.length) return paths;
  }
  return pathsFromClipboardText(clipboardText(data, "text/plain") || clipboardText(data, "text"));
}

export function clipboardFilePaths(event: { clipboardData?: DataTransfer | null }): string[] {
  return transferFilePaths(event.clipboardData);
}

export function clipboardHasAttachable(event: { clipboardData?: DataTransfer | null }): boolean {
  const data = event.clipboardData;
  if (!data) return false;
  if ((data.files || []).length) return true;
  if (clipboardItems(data).some((item) => item.kind === "file" || isMediaClipboardType(item.type))) {
    return true;
  }
  return transferFilePaths(data).length > 0;
}

export function filesFromAttachedPayload(
  files: { name: string; type?: string; contentBase64: string }[],
): File[] {
  return files.map((item, index) => {
    const binary = atob(item.contentBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return nameClipboardFile(new File([bytes], item.name, { type: item.type || "" }), index);
  });
}

function pushUnique(out: File[], seen: Set<File>, file: File | null): void {
  if (!file || seen.has(file)) return;
  seen.add(file);
  out.push(file);
}

export function pastedFiles(event: { clipboardData?: DataTransfer | null }): File[] {
  const data = event.clipboardData;
  if (!data) return [];
  const raw: File[] = [];
  const seen = new Set<File>();
  for (const file of Array.from(data.files || [])) pushUnique(raw, seen, file);
  for (const item of clipboardItems(data)) {
    if (item.kind === "file" || isMediaClipboardType(item.type)) {
      pushUnique(raw, seen, item.getAsFile());
    }
  }
  return raw.map((file, index) => nameClipboardFile(file, index));
}

export async function readClipboardFiles(event?: {
  clipboardData?: DataTransfer | null;
}): Promise<File[]> {
  const sync = event ? pastedFiles(event) : [];
  if (sync.length) return sync;
  const clipboard = globalThis.navigator?.clipboard as
    | { read?: () => Promise<Array<{ types: string[]; getType: (type: string) => Promise<Blob> }>> }
    | undefined;
  if (!clipboard || typeof clipboard.read !== "function") return [];
  try {
    const items = await clipboard.read();
    const files: File[] = [];
    for (const item of items) {
      for (const type of item.types || []) {
        if (!isMediaClipboardType(type)) continue;
        const blob = await item.getType(type);
        files.push(nameClipboardFile(new File([blob], "", { type: blob.type || type }), files.length));
      }
    }
    return files;
  } catch {
    return [];
  }
}

export function droppedFiles(event: { dataTransfer?: DataTransfer | null }): File[] {
  return Array.from(event.dataTransfer?.files || []);
}

function totalBytes(files: File[]): number {
  return files.reduce((sum, file) => sum + (file.size || 0), 0);
}

export function addPendingFiles(
  current: PendingFile[],
  incoming: File[],
): { files: PendingFile[]; error: string } {
  const next = [...current];
  for (const file of incoming) {
    const media = previewKind(file) !== "file";
    if (!file || (file.size <= 0 && !media)) {
      return { files: current, error: "Empty files cannot be attached" };
    }
    if (file.size > MAX_UPLOAD_FILE_BYTES) {
      return { files: current, error: `${file.name || "File"} is larger than 25 MB` };
    }
    if (next.length >= MAX_UPLOAD_FILES) {
      return { files: current, error: `At most ${MAX_UPLOAD_FILES} files` };
    }
    if (totalBytes(next.map((item) => item.file)) + file.size > MAX_UPLOAD_TOTAL_BYTES) {
      return { files: current, error: "Those files are too large together" };
    }
    next.push({
      id: `${file.name}-${file.size}-${file.lastModified}-${next.length}`,
      file,
    });
  }
  return { files: next, error: "" };
}

export function readFileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}
