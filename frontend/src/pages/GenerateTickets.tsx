import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import LogoManager from "../components/LogoManager";
import TicketCard from "../components/TicketCard";
import {
  downloadTicketSheet,
  errorMessage,
  fetchQrObjectUrl,
  generateTickets,
  getRaffle,
  listTickets,
} from "../api/client";
import type { Ticket } from "../api/types";

export default function GenerateTickets() {
  const { raffleId = "" } = useParams();
  const navigate = useNavigate();

  const [raffleName, setRaffleName] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ticketId -> object URL for its QR PNG. Revoked on unmount.
  const [qrUrls, setQrUrls] = useState<Record<string, string>>({});
  const qrUrlsRef = useRef<Record<string, string>>({});
  qrUrlsRef.current = qrUrls;
  // Ticket ids whose QR fetch is in flight, so re-renders don't re-request.
  const fetchingRef = useRef<Set<string>>(new Set());

  async function refresh() {
    const [raffle, ts] = await Promise.all([
      getRaffle(raffleId),
      listTickets(raffleId),
    ]);
    setRaffleName(raffle.name);
    setTickets(ts);
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
    // Revoke every object URL we created when leaving the page.
    return () => {
      Object.values(qrUrlsRef.current).forEach(URL.revokeObjectURL);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raffleId]);

  // Lazily fetch a QR object URL for any ticket that doesn't have one yet.
  // Depends only on `tickets`: in-flight ids are tracked in a ref and existing
  // urls are read from qrUrlsRef, so storing one URL doesn't re-fire the effect
  // (which would cancel/restart the whole batch).
  useEffect(() => {
    let cancelled = false;
    const missing = tickets.filter(
      (t) => !qrUrlsRef.current[t.id] && !fetchingRef.current.has(t.id)
    );
    if (missing.length === 0) return;
    missing.forEach((t) => fetchingRef.current.add(t.id));
    (async () => {
      for (const t of missing) {
        try {
          const url = await fetchQrObjectUrl(t.id);
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          setQrUrls((prev) => ({ ...prev, [t.id]: url }));
        } catch {
          /* leave this card without a QR rather than failing the page */
        } finally {
          fetchingRef.current.delete(t.id);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tickets]);

  async function onGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await generateTickets(raffleId, count);
      await refresh();
    } catch (err) {
      setError(errorMessage(err, "Could not generate tickets."));
    } finally {
      setBusy(false);
    }
  }

  async function onDownloadSheet() {
    try {
      await downloadTicketSheet(raffleId, raffleName || "raffle");
    } catch (err) {
      setError(errorMessage(err, "Could not download print sheet."));
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="no-print">
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mb-4 text-sm text-gray-500 hover:text-brand"
        >
          ← Back to dashboard
        </button>
        <h1 className="text-2xl font-bold text-gray-900">
          Tickets — {raffleName}
        </h1>
        <p className="mb-6 text-sm text-gray-500">
          Generate physical tickets. Each QR encodes a unique, unguessable
          registration link — never the ticket number.
        </p>

        <form
          onSubmit={onGenerate}
          className="mb-6 flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow"
        >
          <div>
            <label
              htmlFor="count"
              className="block text-sm font-medium text-gray-700"
            >
              How many?
            </label>
            <input
              id="count"
              type="number"
              min={1}
              max={10000}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="mt-1 w-32 rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
          <button
            type="submit"
            disabled={busy || count < 1}
            className="rounded-lg bg-brand px-4 py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? "Generating…" : "Generate"}
          </button>
          {tickets.length > 0 && (
            <>
              <button
                type="button"
                onClick={onDownloadSheet}
                className="rounded-lg border border-gray-300 px-4 py-2 font-semibold text-gray-700 hover:bg-gray-50"
              >
                Download print sheet (PNG)
              </button>
              <button
                type="button"
                onClick={() => window.print()}
                className="rounded-lg border border-gray-300 px-4 py-2 font-semibold text-gray-700 hover:bg-gray-50"
              >
                Print these cards
              </button>
            </>
          )}
          {error && <p className="w-full text-sm text-red-600">{error}</p>}
        </form>

        <div className="mb-6">
          <LogoManager raffleId={raffleId} />
        </div>

        <p className="mb-4 text-sm font-medium text-gray-600">
          {tickets.length} ticket{tickets.length === 1 ? "" : "s"} generated
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            qrUrl={qrUrls[t.id] ?? ""}
          />
        ))}
      </div>
    </div>
  );
}
