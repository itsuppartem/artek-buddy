import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { PairingPage } from "./pages/Pairing";
import { ShellPage } from "./pages/Shell";

export function App() {
  const [paired, setPaired] = useState<boolean | null>(null);

  useEffect(() => {
    api.local
      .status()
      .then((status) => setPaired(status.paired))
      .catch(() => setPaired(false));
  }, []);

  if (paired === null) {
    return <div className="h-full bg-[#050506]" />;
  }
  if (!paired) {
    return <PairingPage onPaired={() => setPaired(true)} />;
  }
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/app" element={<ShellPage />} />
      <Route path="/app/:botId" element={<ShellPage />} />
    </Routes>
  );
}
