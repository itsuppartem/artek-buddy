import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { PairingPage } from "./pages/Pairing";
import { ShellPage } from "./pages/Shell";

export function App() {
  const [paired, setPaired] = useState<boolean | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    api.local
      .status()
      .then((status) => {
        setBootError(null);
        setPaired(status.paired);
      })
      .catch((err: unknown) => {
        setBootError(err instanceof Error ? err.message : "Could not reach the local client");
      });
  }, []);

  if (bootError) {
    return (
      <div className="flex h-full items-center justify-center bg-[#050506] px-6 text-center">
        <div data-testid="proxy-error" className="max-w-sm text-[14px] leading-6 text-[#F0AAA0]">
          <div>{bootError}</div>
          <button
            type="button"
            className="mt-3 text-[13px] font-medium text-[#ECECEE] underline underline-offset-2"
            onClick={() => window.location.reload()}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }
  if (paired === null) {
    return <div className="h-full bg-[#050506]" />;
  }
  if (!paired) {
    return <PairingPage onPaired={() => setPaired(true)} />;
  }
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/app/:botId?" element={<ShellPage />} />
    </Routes>
  );
}
