export function isCronShape(value: string): boolean {
  const parts = value.trim().split(/\s+/);
  return parts.length === 5 && parts.every((part) => part.length > 0);
}

export function formatNextRunAt(iso: string): string {
  return iso.replace(/\.\d+/, "").replace("T", " ").replace("Z", " UTC");
}
