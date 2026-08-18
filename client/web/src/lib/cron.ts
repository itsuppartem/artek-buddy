export function isCronShape(value: string): boolean {
  const parts = value.trim().split(/\s+/);
  return parts.length === 5 && parts.every((part) => part.length > 0);
}
