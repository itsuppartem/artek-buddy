import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { formatPairingCode } from "../lib/pairing";
import { Button } from "../ui/button";
import { WindowChrome } from "../ui/window-chrome";

export function PairingPage({ onPaired }: { onPaired: () => void }) {
  const [url, setUrl] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("This computer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.local
      .status()
      .then((status) => {
        if (status.url) setUrl(status.url);
      })
      .catch(() => {
        // stay on the form; the loopback status route is optional while typing
      });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.local.pair({
        url: url.trim() || undefined,
        pairingCode: code.trim(),
        name: name.trim() || "This computer",
        platform: "linux",
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
    <div className="flex h-full flex-col bg-[#050506] text-[#dfdfe2]">
      <div className="flex items-center gap-3 px-4 pt-3">
        <WindowChrome />
        <span className="text-[13px] text-[#6C6C70]">Artek Buddy</span>
      </div>
      <div className="flex flex-1 items-center justify-center px-6 pb-16">
        <form
          onSubmit={submit}
          data-testid="pairing"
          className="w-full max-w-[420px] rounded-2xl border border-[#202023] bg-[#0D0D0E] p-6"
        >
          <div className="text-[21px] font-medium text-[#ECECEE]">Pair this computer</div>
          <p className="mt-2 text-[14px] leading-6 text-[#85858A]">
            On the host, mint a pairing code. Enter it here. The page never sees the device
            token.
          </p>
          <label className="mt-5 block text-[12.5px] text-[#6C6C70]">
            Host URL
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://host.example"
              autoComplete="off"
              className="mt-1.5 h-10 w-full rounded-xl border border-[#202023] bg-[#141416] px-3 text-[14px] text-[#ECECEE] outline-none focus:border-[#3A3A40]"
            />
          </label>
          <label className="mt-3 block text-[12.5px] text-[#6C6C70]">
            Pairing code
            <input
              value={code}
              onChange={(event) => setCode(formatPairingCode(event.target.value))}
              placeholder="XXXX-XXXX"
              autoComplete="off"
              spellCheck={false}
              className="mt-1.5 h-10 w-full rounded-xl border border-[#202023] bg-[#141416] px-3 font-mono text-[15px] tracking-[0.18em] text-[#ECECEE] outline-none focus:border-[#3A3A40]"
            />
          </label>
          <label className="mt-3 block text-[12.5px] text-[#6C6C70]">
            Device name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1.5 h-10 w-full rounded-xl border border-[#202023] bg-[#141416] px-3 text-[14px] text-[#ECECEE] outline-none focus:border-[#3A3A40]"
            />
          </label>
          {error ? (
            <div data-testid="pairing-error" className="mt-3 text-[13px] text-[#E38A8A]">
              {error}
            </div>
          ) : null}
          <Button type="submit" variant="cream" className="mt-5 w-full" disabled={busy || !code}>
            {busy ? "Pairing…" : "Pair"}
          </Button>
          <p className="mt-4 text-[12.5px] leading-5 text-[#6C6C70]">
            Host command: <span className="font-mono text-[#9A9AA0]">python -m artek_buddy pair</span>
          </p>
        </form>
      </div>
    </div>
  );
}
