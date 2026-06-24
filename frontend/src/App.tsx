import { useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AdminDashboard from "./pages/AdminDashboard";
import CreateRaffle from "./pages/CreateRaffle";
import GenerateTickets from "./pages/GenerateTickets";
import Register from "./pages/Register";
import { clearApiKey, getApiKey, setApiKey } from "./api/client";

/** Prompts for the org API key once, then stores it for authenticated calls. */
function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [hasKey, setHasKey] = useState(() => Boolean(getApiKey()));
  const [value, setValue] = useState("");

  if (hasKey) return <>{children}</>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!value.trim()) return;
          setApiKey(value);
          setHasKey(true);
        }}
        className="w-full max-w-sm rounded-xl bg-white p-6 shadow"
      >
        <h1 className="text-xl font-bold text-gray-900">Raffler admin</h1>
        <p className="mb-4 mt-1 text-sm text-gray-500">
          Enter your organization API key to manage raffles. It's stored only in
          this browser.
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="rk_…"
          autoComplete="off"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="mt-3 w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          Continue
        </button>
      </form>
    </div>
  );
}

function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <ApiKeyGate>
      <div className="min-h-screen bg-gray-50">
        <header className="no-print border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <span className="text-lg font-bold text-brand">Raffler</span>
            <button
              type="button"
              onClick={() => {
                clearApiKey();
                window.location.reload();
              }}
              className="text-sm text-gray-500 hover:text-brand"
            >
              Sign out
            </button>
          </div>
        </header>
        {children}
      </div>
    </ApiKeyGate>
  );
}

export default function App() {
  const location = useLocation();
  // The public registration route must never sit behind the admin key gate.
  const isPublic = location.pathname.startsWith("/register/");

  if (isPublic) {
    return (
      <Routes>
        <Route path="/register/:token" element={<Register />} />
      </Routes>
    );
  }

  return (
    <AdminShell>
      <Routes>
        <Route path="/" element={<AdminDashboard />} />
        <Route path="/raffles/new" element={<CreateRaffle />} />
        <Route path="/raffles/:raffleId/tickets" element={<GenerateTickets />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AdminShell>
  );
}
