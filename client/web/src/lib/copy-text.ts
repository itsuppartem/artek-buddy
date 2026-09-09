type CopyTextOptions = {
  writeText?: (text: string) => Promise<void>;
  fallback?: (text: string) => boolean;
};

function legacyCopy(text: string): boolean {
  if (!globalThis.document) return false;
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  try {
    return document.execCommand("copy");
  } finally {
    input.remove();
  }
}

export async function copyText(text: string, options: CopyTextOptions = {}): Promise<boolean> {
  const writeText =
    options.writeText ??
    globalThis.navigator?.clipboard?.writeText?.bind(globalThis.navigator.clipboard);
  if (writeText) {
    try {
      await writeText(text);
      return true;
    } catch {
      // Older WebKit builds expose clipboard.writeText but reject it.
    }
  }
  return (options.fallback ?? legacyCopy)(text);
}
