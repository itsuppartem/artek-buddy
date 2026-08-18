function camelKey(key: string): string {
  return key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

function snakeKey(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

export function camelize<T>(value: unknown): T {
  if (Array.isArray(value)) {
    return value.map((item) => camelize(item)) as T;
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[camelKey(key)] = camelize(item);
    }
    return out as T;
  }
  return value as T;
}

export function snakify(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => snakify(item));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[snakeKey(key)] = snakify(item);
    }
    return out;
  }
  return value;
}
