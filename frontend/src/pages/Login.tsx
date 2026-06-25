import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage, googleAuthUrl, login } from "../api/client";

const GOOGLE_ERRORS: Record<string, string> = {
  google_failed: "Google sign-in failed. Please try again.",
  email_unverified: "Your Google email isn't verified.",
};

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(
    GOOGLE_ERRORS[params.get("error") ?? ""] ?? null
  );

  // After login, return to where the seller was headed (e.g. a scanned ticket).
  // Only allow same-origin relative paths (no "//host" protocol-relative URLs).
  const rawNext = params.get("next");
  const next =
    rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not sign in."));
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle() {
    setError(null);
    try {
      window.location.href = await googleAuthUrl();
    } catch {
      setError("Google sign-in isn't available right now.");
    }
  }

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        <h1 className="text-xl font-bold text-brand">Raffler</h1>
        <p className="mb-4 mt-1 text-sm text-gray-500">Sign in to your account.</p>

        <button
          type="button"
          onClick={onGoogle}
          className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg border border-gray-300 py-2 font-semibold text-gray-700 hover:bg-gray-50"
        >
          <span aria-hidden="true">G</span> Continue with Google
        </button>

        <div className="mb-4 flex items-center gap-3 text-xs text-gray-400">
          <span className="h-px flex-1 bg-gray-200" /> or <span className="h-px flex-1 bg-gray-200" />
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
              autoComplete="email"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
              autoComplete="current-password"
            />
          </div>
          <p role="alert" aria-live="assertive" className="text-sm text-red-600">
            {error ?? ""}
          </p>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-gray-500">
          No account?{" "}
          <Link to="/signup" className="font-medium text-brand hover:underline">
            Sign up free
          </Link>
        </p>
      </div>
    </div>
  );
}
