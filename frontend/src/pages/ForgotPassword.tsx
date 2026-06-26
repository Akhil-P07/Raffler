import { useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage, requestPasswordReset } from "../api/client";

/** Public page: request a password-reset email. The server always responds the
 *  same way, so this never reveals whether an account exists for the address. */
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setSent(await requestPasswordReset(email));
    } catch (err) {
      setError(errorMessage(err, "Could not send the reset email."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        <h1 className="text-xl font-bold text-brand">Forgot password</h1>
        <p className="mb-4 mt-1 text-sm text-gray-500">
          Enter your email and we'll send you a reset link.
        </p>

        {sent ? (
          <p className="rounded-lg bg-green-50 px-3 py-3 text-sm text-green-700">
            {sent}
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-3">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700"
              >
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
            <p role="alert" aria-live="assertive" className="text-sm text-red-600">
              {error ?? ""}
            </p>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
            >
              {busy ? "Sending…" : "Send reset link"}
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
