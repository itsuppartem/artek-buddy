export function formatPairingCode(value: string): string {
  const raw = value
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, 8);
  if (raw.length <= 4) return raw;
  return `${raw.slice(0, 4)}-${raw.slice(4)}`;
}

export type LocalStatus = {
  paired: boolean;
  url: string;
  nonce: string;
};

export type PairedDevice = {
  id: string;
  name: string;
  platform: string;
  createdAt?: string;
};
