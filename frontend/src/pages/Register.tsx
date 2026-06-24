import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  errorMessage,
  getRegisterInfo,
  submitRegistration,
} from "../api/client";
import type { RegisterConfirmation, RegisterInfo } from "../api/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; info: RegisterInfo }
  | { kind: "notfound" }
  | { kind: "done"; confirmation: RegisterConfirmation };

/**
 * Public buyer page, opened by scanning a ticket's QR. Token-based: no API
 * key, no org data. Submit is guarded against double-submit.
 */
export default function Register() {
  const { token = "" } = useParams();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Hard guard so a fast double-tap can't fire two POSTs.
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    getRegisterInfo(token)
      .then((info) => {
        if (cancelled) return;
        setState(
          info.registered
            ? // Already registered: surface it but don't pretend it's a fresh
              // confirmation.
              { kind: "ready", info }
            : { kind: "ready", info }
        );
      })
      .catch(() => !cancelled && setState({ kind: "notfound" }));
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current || submitting) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const confirmation = await submitRegistration(token, name, email);
      setState({ kind: "done", confirmation });
    } catch (err) {
      setError(errorMessage(err, "Could not register. Please try again."));
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow">
        {state.kind === "loading" && (
          <p className="text-center text-gray-500">Loading…</p>
        )}

        {state.kind === "notfound" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">🎫</div>
            <h1 className="text-lg font-bold text-gray-900">Ticket not found</h1>
            <p className="mt-2 text-sm text-gray-600">
              This registration link isn't valid. Double-check you scanned the
              QR on your ticket.
            </p>
          </div>
        )}

        {state.kind === "ready" && state.info.registered && (
          <div className="text-center">
            <div className="mb-2 text-4xl">✅</div>
            <h1 className="text-lg font-bold text-gray-900">
              Already registered
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              Ticket #{state.info.ticket_number} for{" "}
              <span className="font-medium">{state.info.raffle_name}</span> is
              already entered. You're all set — good luck!
            </p>
          </div>
        )}

        {state.kind === "ready" && !state.info.registered && (
          <>
            <h1 className="text-center text-xl font-bold text-gray-900">
              {state.info.raffle_name}
            </h1>
            <p className="mb-4 mt-1 text-center text-sm text-gray-500">
              Registering ticket #{state.info.ticket_number}
            </p>
            <form onSubmit={onSubmit} className="space-y-3" noValidate>
              <div>
                <label
                  htmlFor="name"
                  className="block text-sm font-medium text-gray-700"
                >
                  Name
                </label>
                <input
                  id="name"
                  type="text"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  autoComplete="name"
                />
              </div>
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
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  autoComplete="email"
                  inputMode="email"
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
              >
                {submitting ? "Registering…" : "Register"}
              </button>
            </form>
            <p className="mt-3 text-center text-xs text-gray-400">
              We only collect your name and email to contact you if you win.
            </p>
          </>
        )}

        {state.kind === "done" && (
          <div className="text-center">
            <div className="mb-2 text-4xl">🎉</div>
            <h1 className="text-lg font-bold text-gray-900">You're entered!</h1>
            <p className="mt-2 text-sm text-gray-600">
              Thanks {state.confirmation.name} — ticket #
              {state.confirmation.ticket_number} for{" "}
              <span className="font-medium">
                {state.confirmation.raffle_name}
              </span>{" "}
              is registered. Good luck!
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
