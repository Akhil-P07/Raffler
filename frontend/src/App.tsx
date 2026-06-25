import { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import AdminDashboard from "./pages/AdminDashboard";
import AuthCallback from "./pages/AuthCallback";
import CreateRaffle from "./pages/CreateRaffle";
import GenerateTickets from "./pages/GenerateTickets";
import Login from "./pages/Login";
import OrgSettings from "./pages/OrgSettings";
import Register from "./pages/Register";
import Signup from "./pages/Signup";
import { clearSession, getMe, getSession, isUnauthorized } from "./api/client";
import type { Me } from "./api/types";

function AdminShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch((err) => {
        // A bad/expired session resolves to the login screen.
        if (isUnauthorized(err)) {
          clearSession();
          navigate("/login", { replace: true });
        }
      });
  }, [navigate]);

  function signOut() {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="no-print border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-bold text-brand">
            Raffler
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {me && (
              <>
                <span className="hidden text-gray-600 sm:inline">{me.email}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    me.org.plan === "club"
                      ? "bg-brand/10 text-brand-dark"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {me.org.plan === "club" ? "Club" : "Free"}
                </span>
              </>
            )}
            <Link to="/settings" className="text-gray-500 hover:text-brand">
              Settings
            </Link>
            <button
              type="button"
              onClick={signOut}
              className="text-gray-500 hover:text-brand"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}

export default function App() {
  const { pathname, search } = useLocation();

  // Auth screens (no session required).
  if (
    pathname === "/login" ||
    pathname === "/signup" ||
    pathname.startsWith("/auth/callback")
  ) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
      </Routes>
    );
  }

  // Everything else — including ticket registration — requires a session.
  // Preserve where the seller was headed (e.g. a scanned /register/<token>).
  if (!getSession()) {
    const next = encodeURIComponent(pathname + search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return (
    <AdminShell>
      <Routes>
        <Route path="/" element={<AdminDashboard />} />
        <Route path="/raffles/new" element={<CreateRaffle />} />
        <Route path="/raffles/:raffleId/tickets" element={<GenerateTickets />} />
        <Route path="/register/:token" element={<Register />} />
        <Route path="/settings" element={<OrgSettings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AdminShell>
  );
}
