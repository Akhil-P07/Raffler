import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import LogoManager from "../components/LogoManager";
import TicketCard from "../components/TicketCard";
import {
  downloadTicketSheet,
  errorMessage,
  generateTickets,
  getRaffle,
  listTickets,
} from "../api/client";
import type { Ticket } from "../api/types";

export default function GenerateTickets() {
  const { raffleId = "" } = useParams();
  const navigate = useNavigate();

  const [raffleName, setRaffleName] = useState("");
  const [eventCode, setEventCode] = useState<string | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // QR codes load on demand (one request each). "Reveal all" flips this on so
  // every card fetches its own QR; otherwise each loads only when clicked.
  const [revealAll, setRevealAll] = useState(false);

  async function refresh() {
    const [raffle, ts] = await Promise.all([
      getRaffle(raffleId),
      listTickets(raffleId),
    ]);
    setRaffleName(raffle.name);
    setEventCode(raffle.event_code);
    setTickets(ts);
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raffleId]);

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

  async function onDownloadPdf() {
    if (downloading) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadTicketSheet(raffleId, raffleName || "raffle");
    } catch (err) {
      setError(errorMessage(err, "Could not download the PDF."));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 text-sm text-gray-500 hover:text-brand"
      >
        ← Back to dashboard
      </button>
      <h1 className="text-2xl font-bold text-gray-900">
        Tickets — {raffleName}
        {eventCode && (
          <span className="ml-2 align-middle text-base font-medium text-gray-400">
            ({eventCode})
          </span>
        )}
      </h1>
      <p className="mb-6 text-sm text-gray-500">
        Each ticket shows its serial (#{eventCode ?? "CODE"}-1, …) and a QR the
        organizer scans to register a buyer. QR codes load on demand — click
        “Show QR” on a ticket, or “Reveal all”. Download the A4 PDF to print in
        bulk.
      </p>

      <form
        onSubmit={onGenerate}
        className="mb-6 flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow"
      >
        <div>
          <label htmlFor="count" className="block text-sm font-medium text-gray-700">
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
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={downloading}
            className="rounded-lg border border-gray-300 px-4 py-2 font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            {downloading ? "Preparing PDF…" : "Download A4 PDF"}
          </button>
        )}
        {error && <p className="w-full text-sm text-red-600">{error}</p>}
      </form>

      <div className="mb-6">
        <LogoManager raffleId={raffleId} />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-gray-600">
          {tickets.length} ticket{tickets.length === 1 ? "" : "s"} generated
        </p>
        {tickets.length > 0 && !revealAll && (
          <button
            type="button"
            onClick={() => setRevealAll(true)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
          >
            Reveal all QR codes
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            eventCode={eventCode}
            reveal={revealAll}
          />
        ))}
      </div>
    </div>
  );
}
