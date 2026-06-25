import { useCallback, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import AdminDashboard from "./pages/AdminDashboard";
import AcceptInvite from "./pages/AcceptInvite";
import AuthCallback from "./pages/AuthCallback";
import CreateRaffle from "./pages/CreateRaffle";
import GenerateTickets from "./pages/GenerateTickets";
import Login from "./pages/Login";
import OrgSettings from "./pages/OrgSettings";
import Register from "./pages/Register";
import Signup from "./pages/Signup";
import {
  clearSession,
  getMe,
  getSession,
  isUnauthorized,
  selectOrg,
} from "./api/client";
import { MeContext } from "./auth/MeContext";
import type { Me } from "./api/types";

function AdminShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [switching, setSwitching] = useState(false);

  const reload = useCallback(async () => {
    try {
      setMe(await getMe());
    } catch (err) {
      if (isUnauthorized(err)) {
        clearSession();
        navigate("/login", { replace: true });
      }
    }
  }, [navigate]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onSwitchOrg(orgId: string) {
    if (orgId === me?.org.id || switching) return;
    setSwitching(true);
    try {
      await selectOrg(orgId);
      await reload();
      navigate("/", { replace: true });
    } finally {
      setSwitching(false);
    }
  }

  function signOut() {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <MeContext.Provider value={{ me, reload }}>
      <div className="min-h-screen bg-gray-50">
        <header className="no-print border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
            <Link to="/" className="text-lg font-bold text-brand">
              Raffler
            </Link>
            <div className="flex items-center gap-3 text-sm">
              {me && me.orgs.length > 1 ? (
                <select
                  aria-label="Switch organization"
                  value={me.org.id}
                  disabled={switching}
                  onChange={(e) => onSwitchOrg(e.target.value)}
                  className="rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-brand focus:outline-none"
                >
                  {me.orgs.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name} ({o.role})
                    </option>
                  ))}
                </select>
              ) : (
                me && <span className="font-medium text-gray-700">{me.org.name}</span>
              )}
              {me && (
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    me.org.plan === "club"
                      ? "bg-brand/10 text-brand-dark"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {me.org.plan === "club" ? "Club" : "Free"}
                </span>
              )}
              {me && (
                <span className="hidden text-gray-500 sm:inline">{me.email}</span>
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
    </MeContext.Provider>
  );
}

export default function App() {
  const { pathname, search } = useLocation();

  // Public, no session: auth screens + invite acceptance.
  if (
    pathname === "/login" ||
    pathname === "/signup" ||
    pathname === "/accept-invite" ||
    pathname.startsWith("/auth/callback")
  ) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/accept-invite" element={<AcceptInvite />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
      </Routes>
    );
  }

  // Everything else — including ticket registration — requires a session.
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
