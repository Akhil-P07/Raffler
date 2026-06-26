import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { errorMessage, resetPassword } from "../api/client";

/** Public page: set a new password from the emailed reset link's token. */
export default function ResetPassword() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token, password);
      navigate("/login?reset=1", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not reset your password."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        <h1 className="text-xl font-bold text-brand">Reset password</h1>
        <p className="mb-4 mt-1 text-sm text-gray-500">
          Choose a new password for your account.
        </p>

        {!token ? (
          <p className="rounded-lg bg-red-50 px-3 py-3 text-sm text-red-700">
            This reset link is missing its token. Request a new one from the
            forgot-password page.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700"
              >
                New password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={field}
                autoComplete="new-password"
              />
            </div>
            <div>
              <label
                htmlFor="confirm"
                className="block text-sm font-medium text-gray-700"
              >
                Confirm password
              </label>
              <input
                id="confirm"
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={field}
                autoComplete="new-password"
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
              {busy ? "Resetting…" : "Reset password"}
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-gray-500">
          <Link to="/login" className="font-medium text-brand hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
