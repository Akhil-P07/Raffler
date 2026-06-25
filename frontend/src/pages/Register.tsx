import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  errorMessage,
  getRegisterInfo,
  isUnauthorized,
  submitRegistration,
} from "../api/client";
import type { RegisterConfirmation, RegisterInfo } from "../api/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; info: RegisterInfo }
  | { kind: "already"; info: RegisterInfo }
  | { kind: "notowned" }
  | { kind: "notfound" }
  | { kind: "done"; confirmation: RegisterConfirmation };

/**
 * Seller-side ticket registration. The seller scans a ticket's QR (which opens
 * this page in their logged-in portal); the server confirms the ticket belongs
 * to their org, then the seller enters the buyer's name + email. Buyers never
 * self-register.
 */
export default function Register() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    getRegisterInfo(token)
      .then((info) => {
        if (cancelled) return;
        if (!info.owned) setState({ kind: "notowned" });
        else if (info.registered) setState({ kind: "already", info });
        else setState({ kind: "ready", info });
      })
      .catch((err) => {
        if (cancelled) return;
        // A 401 means the session lapsed; the route guard will send us to login.
        if (isUnauthorized(err)) navigate("/login", { replace: true });
        else setState({ kind: "notfound" });
      });
    return () => {
      cancelled = true;
    };
  }, [token, navigate]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current || submitting) return;
    if (!name.trim()) {
      setError("Please enter the buyer's name.");
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const confirmation = await submitRegistration(token, name, email);
      setState({ kind: "done", confirmation });
    } catch (err) {
      setError(errorMessage(err, "Could not register this ticket."));
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        {state.kind === "loading" && (
          <p className="text-center text-gray-500">Loading ticket…</p>
        )}

        {state.kind === "notfound" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">🎫</div>
            <h1 className="text-lg font-bold text-gray-900">Ticket not found</h1>
            <p className="mt-2 text-sm text-gray-600">
              This QR doesn't match a ticket. Re-scan the ticket and try again.
            </p>
          </div>
        )}

        {state.kind === "notowned" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">🚫</div>
            <h1 className="text-lg font-bold text-gray-900">
              Not your organization's ticket
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              This ticket belongs to a different organization, so it can't be
              registered from your account.
            </p>
          </div>
        )}

        {state.kind === "already" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">✅</div>
            <h1 className="text-lg font-bold text-gray-900">
              Already registered
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              Ticket #{state.info.ticket_number} for{" "}
              <span className="font-medium">{state.info.raffle_name}</span> is
              registered to:
            </p>
            <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-left">
              <p className="font-semibold text-gray-900">
                {state.info.registrant_name ?? "—"}
              </p>
              <p className="text-sm text-gray-600">
                {state.info.registrant_email ?? ""}
              </p>
            </div>
          </div>
        )}

        {state.kind === "ready" && (
          <>
            <h1 className="text-center text-xl font-bold text-gray-900">
              {state.info.raffle_name}
            </h1>
            <p className="mb-4 mt-1 text-center text-sm text-gray-500">
              Registering ticket #{state.info.ticket_number} — enter the buyer's
              details.
            </p>
            <form onSubmit={onSubmit} className="space-y-3" noValidate>
              <div>
                <label
                  htmlFor="name"
                  className="block text-sm font-medium text-gray-700"
                >
                  Buyer name
                </label>
                <input
                  id="name"
                  type="text"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-3 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  autoComplete="off"
                />
              </div>
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700"
                >
                  Buyer email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-3 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  autoComplete="off"
                  inputMode="email"
                />
              </div>
              <p
                role="alert"
                aria-live="assertive"
                className="text-sm text-red-600"
              >
                {error ?? ""}
              </p>
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-brand py-3 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
              >
                {submitting ? "Registering…" : "Register ticket"}
              </button>
            </form>
          </>
        )}

        {state.kind === "done" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">🎉</div>
            <h1 className="text-lg font-bold text-gray-900">Registered!</h1>
            <p className="mt-2 text-sm text-gray-600">
              Ticket #{state.confirmation.ticket_number} for{" "}
              <span className="font-medium">
                {state.confirmation.raffle_name}
              </span>{" "}
              is now entered under {state.confirmation.name}.
            </p>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="mt-4 w-full rounded-lg border border-gray-300 py-2 font-semibold text-gray-700 hover:bg-gray-50"
            >
              Back to dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
