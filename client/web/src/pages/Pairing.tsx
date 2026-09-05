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
    <div className="pairing-screen flex h-full flex-col bg-ink text-paper">
      <div className="app-drag flex min-h-14 items-center gap-3 px-4 pt-[env(safe-area-inset-top,0px)]">
        {hostPage ? null : <WindowChrome />}
        <img src="/favicon.png" alt="" width={22} height={22} className="rounded-[7px]" />
        <span className="text-[12px] font-semibold text-mute">Artek Buddy</span>
      </div>
      <div className="ab-scroll flex flex-1 items-start justify-center overflow-y-auto px-4 py-4 sm:px-6 md:items-center md:py-6 md:pb-14">
        <form
          onSubmit={submit}
          data-testid="pairing"
          className="grid w-full max-w-[820px] overflow-hidden rounded-[20px] border border-hairline bg-plate shadow-[0_28px_80px_rgba(25,48,82,0.14)] md:grid-cols-[0.9fr_1.1fr]"
        >
          <div className="relative min-h-[190px] overflow-hidden bg-soft-blue p-5 md:flex md:min-h-[520px] md:flex-col md:justify-between md:p-8">
            <div>
              <p className="font-mono text-[9px] tracking-[0.08em] text-tan uppercase">
                Private control surface
              </p>
              <h1 className="mt-3 max-w-[13rem] text-[23px] font-bold leading-[1.05] tracking-[-0.045em] text-paper md:max-w-[16rem] md:text-[34px]">
                One code. Then Artek is yours.
              </h1>
              <p className="mt-3 hidden max-w-[18rem] text-[12.5px] leading-5 text-mute md:block">
                Pair this screen with your host. No account form and no credential copied into the
                page.
              </p>
            </div>
            <img
              data-testid="app-mark"
              src="/pairing-mark.png"
              alt=""
              width={360}
              height={360}
              className="pairing-mascot pointer-events-none absolute right-0 bottom-0 w-[175px] object-contain md:static md:mx-auto md:-mb-12 md:w-[min(100%,330px)]"
            />
          </div>
          <div className="flex flex-col justify-center p-6 md:p-9">
            <p className="font-mono text-[9px] tracking-[0.08em] text-tan uppercase">
              {hostPage ? "Phone pairing" : "Computer pairing"}
            </p>
            <div className="mt-2 text-[24px] font-bold tracking-[-0.04em] text-paper">
              {hostPage ? "Pair this phone" : "Pair this computer"}
            </div>
            <p className="mt-2 text-[13px] leading-5 text-mute">{PAIRING_BODY}</p>
            <label className="mt-6 block text-[11px] font-semibold text-paper">
              Pairing code
              <input
                value={code}
                onChange={(event) => setCode(formatPairingCode(event.target.value))}
                placeholder="XXXX-XXXX"
                autoComplete="off"
                spellCheck={false}
                className="mt-2 h-12 w-full rounded-[11px] border border-hairline bg-ink px-3.5 text-center font-mono text-[17px] tracking-[0.2em] text-paper"
              />
            </label>
            <details className="mt-4 rounded-[11px] border border-hairline bg-ink px-3.5 py-2.5">
              <summary className="cursor-pointer text-[11.5px] font-semibold text-mute">
                Pairing options
              </summary>
              {hostPage ? null : (
                <label className="mt-3 block text-[11px] text-mute">
                  Host URL
                  <input
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="https://host.example"
                    autoComplete="off"
                    className="mt-1.5 h-10 w-full rounded-[9px] border border-hairline bg-plate px-3 text-[13px] text-paper"
                  />
                </label>
              )}
              <label className="mt-3 block text-[11px] text-mute">
                Device name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-1.5 h-10 w-full rounded-[9px] border border-hairline bg-plate px-3 text-[13px] text-paper"
                />
              </label>
            </details>
            {error ? (
              <div data-testid="pairing-error" className="mt-3 text-[12.5px] text-danger">
                {error}
              </div>
            ) : null}
            {homeHint ? (
              <p data-testid="home-screen-hint" className="mt-3 text-[12px] leading-5 text-tan">
                On iPhone: Share → Add to Home Screen, then open that icon and pair there. Alerts
                work only while the app is open.
              </p>
            ) : null}
            <Button
              type="submit"
              variant="cream"
              className="mt-5 min-h-11 w-full"
              disabled={busy || !code}
            >
              {busy ? "Pairing…" : "Pair"}
            </Button>
            {hostPage ? null : (
              <p
                data-testid="pairing-host-command"
                className="mt-4 text-[10.5px] leading-5 text-mute"
              >
                Create a code on the host:{" "}
                <span className="font-mono text-paper/70">{PAIRING_HOST_COMMAND}</span>
              </p>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
