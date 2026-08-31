import { type FormEvent, useState } from "react";
import { api } from "../api";
import { formatPairingCode, PAIRING_BODY, PAIRING_HOST_COMMAND } from "../lib/pairing";
import {
  isIosDevice,
  isStandaloneDisplay,
  pageSurface,
  shouldShowHomeScreenHint,
} from "../lib/web-notify";
import { Button } from "../ui/button";
import { WindowChrome } from "../ui/window-chrome";

export function PairingPage({
  onPaired,
  initialUrl = "",
}: {
  onPaired: () => void;
  initialUrl?: string;
}) {
  const hostPage = pageSurface() === "host";
  const [url, setUrl] = useState(initialUrl);
  const [code, setCode] = useState("");
  const [name, setName] = useState(hostPage ? "Phone" : "This computer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const homeHint = shouldShowHomeScreenHint({
    surface: pageSurface(),
    ios: isIosDevice(),
    standalone: isStandaloneDisplay(),
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.local.pair({
        url: hostPage ? undefined : url.trim() || undefined,
        pairingCode: code.trim(),
        name: name.trim() || (hostPage ? "Phone" : "This computer"),
        platform: hostPage ? "web" : "linux",
      });
      if (!result.ok) {
        throw new Error(result.error || "pairing failed");
      }
      onPaired();
    } catch (err) {
      setError(err instanceof Error ? err.message : "pairing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-ink text-paper">
      <div className="flex items-center gap-3 px-4 pt-[max(0.75rem,env(safe-area-inset-top,0px))]">
        {hostPage ? null : <WindowChrome />}
        <img src="/favicon.png" alt="" width={18} height={18} className="rounded-[5px]" />
        <span className="text-[13px] text-mute">Artek Buddy</span>
      </div>
      <div className="flex flex-1 items-center justify-center px-6 pb-16">
        <form
          onSubmit={submit}
          data-testid="pairing"
          className="w-full max-w-[420px] rounded-2xl border border-hairline bg-plate p-6"
        >
          <img
            data-testid="app-mark"
            src="/pairing-mark.png"
            alt=""
            width={80}
            height={80}
            className="mb-4 h-20 w-20 rounded-2xl object-cover"
          />
          <div className="font-display text-[21px] font-semibold text-paper">
            {hostPage ? "Pair this phone" : "Pair this computer"}
          </div>
          <p className="mt-2 text-[14px] leading-6 text-mute">{PAIRING_BODY}</p>
          {hostPage ? null : (
            <label className="mt-5 block text-[12.5px] text-mute">
              Host URL
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://host.example"
                autoComplete="off"
                className="mt-1.5 h-10 w-full rounded-[10px] border border-hairline bg-raised px-3 text-[14px] text-paper"
              />
            </label>
          )}
          <label className={`${hostPage ? "mt-5" : "mt-3"} block text-[12.5px] text-mute`}>
            Pairing code
            <input
              value={code}
              onChange={(event) => setCode(formatPairingCode(event.target.value))}
              placeholder="XXXX-XXXX"
              autoComplete="off"
              spellCheck={false}
              className="mt-1.5 h-10 w-full rounded-[10px] border border-hairline bg-raised px-3 font-mono text-[15px] tracking-[0.18em] text-paper"
            />
          </label>
          <label className="mt-3 block text-[12.5px] text-mute">
            Device name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1.5 h-10 w-full rounded-[10px] border border-hairline bg-raised px-3 text-[14px] text-paper"
            />
          </label>
          {error ? (
            <div data-testid="pairing-error" className="mt-3 text-[13px] text-danger">
              {error}
            </div>
          ) : null}
          {homeHint ? (
            <p data-testid="home-screen-hint" className="mt-3 text-[13px] leading-5 text-tan">
              On iPhone: Share → Add to Home Screen, then open that icon and pair there. Alerts need
              Turn on alerts and only fire while this app is open. iPhone will not run it in the
              background.
            </p>
          ) : null}
          <Button type="submit" variant="cream" className="mt-5 w-full" disabled={busy || !code}>
            {busy ? "Pairing…" : "Pair"}
          </Button>
          {hostPage ? null : (
            <p
              data-testid="pairing-host-command"
              className="mt-4 text-[12.5px] leading-5 text-mute"
            >
              On the Pi: <span className="font-mono text-paper/70">{PAIRING_HOST_COMMAND}</span>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
