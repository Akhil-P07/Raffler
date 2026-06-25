import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { acceptInvite, errorMessage, getInviteInfo } from "../api/client";
import type { InviteInfo } from "../api/types";

type State =
  | { kind: "loading" }
  | { kind: "ready"; info: InviteInfo }
  | { kind: "invalid" };

/**
 * Public page reached from an org invitation email (/accept-invite?token=…).
 * A brand-new email sets a password (creating their account + membership); an
 * existing account just joins the org (the emailed token proves email control).
 */
export default function AcceptInvite() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<State>({ kind: "loading" });
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setState({ kind: "invalid" });
      return;
    }
    let cancelled = false;
    getInviteInfo(token)
      .then((info) => !cancelled && setState({ kind: "ready", info }))
      .catch(() => !cancelled && setState({ kind: "invalid" }));
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onAccept(e: React.FormEvent) {
    e.preventDefault();
    if (busy || state.kind !== "ready") return;
    if (state.info.needs_password && password.length < 8) {
      setError("Choose a password of at least 8 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await acceptInvite(
        token,
        state.info.needs_password ? password : undefined
      );
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not accept the invitation."));
      setBusy(false);
    }
  }

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        {state.kind === "loading" && (
          <p className="text-center text-gray-500">Loading invitation…</p>
        )}

        {state.kind === "invalid" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">✉️</div>
            <h1 className="text-lg font-bold text-gray-900">
              Invitation not valid
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              This invitation link is invalid or has expired. Ask the
              organization owner to send a new one.
            </p>
          </div>
        )}

        {state.kind === "ready" && (
          <>
            <h1 className="text-xl font-bold text-gray-900">
              Join {state.info.org_name}
            </h1>
            <p className="mb-4 mt-1 text-sm text-gray-500">
              Invitation for{" "}
              <span className="font-medium">{state.info.email}</span>.
            </p>
            <form onSubmit={onAccept} className="space-y-3">
              {state.info.needs_password && (
                <div>
                  <label
                    htmlFor="password"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Choose a password
                  </label>
                  <input
                    id="password"
                    type="password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={field}
                    autoComplete="new-password"
                  />
                </div>
              )}
              <p role="alert" aria-live="assertive" className="text-sm text-red-600">
                {error ?? ""}
              </p>
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
              >
                {busy ? "Joining…" : "Accept invitation"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
