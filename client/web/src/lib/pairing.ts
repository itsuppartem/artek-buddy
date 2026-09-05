export function formatPairingCode(value: string): string {
  const raw = value
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, 8);
  if (raw.length <= 4) return raw;
  return `${raw.slice(0, 4)}-${raw.slice(4)}`;
}

/** Same Compose exec as README. Deb pairing only; the phone page has no command. */
export const PAIRING_HOST_COMMAND = "docker exec artek-buddy python -m artek_buddy pair";

export const PAIRING_BODY =
  "Create a one-use pairing code on the host. Enter it here, then choose Pair.";

export type LocalStatus = {
  paired: boolean;
  url: string;
  nonce: string;
  surface?: "desktop" | "host";
  windowActive?: boolean | null;
};

export type PairedDevice = {
  id: string;
  name: string;
  platform: string;
  createdAt?: string;
};
