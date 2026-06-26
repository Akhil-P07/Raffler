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
  updateTicketNotes,
} from "../api/client";
import type { Ticket } from "../api/types";

export default function GenerateTickets() {
  const { raffleId = "" } = useParams();
  const navigate = useNavigate();

  const [raffleName, setRaffleName] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [count, setCount] = useState(10);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ticketId -> object URL of its full preview image. Revoked on unmount.
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const previewUrlsRef = useRef<Record<string, string>>({});
  previewUrlsRef.current = previewUrls;
  // Ticket ids whose preview fetch is in flight, so re-renders don't re-request.
  const fetchingRef = useRef<Set<string>>(new Set());

  async function refresh() {
    const [raffle, ts] = await Promise.all([
      getRaffle(raffleId),
      listTickets(raffleId),
    ]);
    setRaffleName(raffle.name);
    setTickets(ts);
  }

  /** Drop all cached previews so they re-render (e.g. after a logo change). */
  function clearPreviews() {
    Object.values(previewUrlsRef.current).forEach(URL.revokeObjectURL);
    fetchingRef.current.clear();
    setPreviewUrls({});
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
    // Revoke every object URL we created when leaving the page.
    return () => {
      Object.values(previewUrlsRef.current).forEach(URL.revokeObjectURL);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raffleId]);

  // Lazily fetch a full-ticket preview for any ticket that doesn't have one.
  // Depends only on `tickets`: in-flight ids are tracked in a ref and existing
  // urls are read from previewUrlsRef, so storing one doesn't re-fire the
  // effect (which would cancel/restart the whole batch).
  useEffect(() => {
    let cancelled = false;
    const missing = tickets.filter(
      (t) => !previewUrlsRef.current[t.id] && !fetchingRef.current.has(t.id)
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
          setPreviewUrls((prev) => ({ ...prev, [t.id]: url }));
        } catch {
          /* leave this card as a placeholder rather than failing the page */
        } finally {
          fetchingRef.current.delete(t.id);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally depends ONLY on `tickets`. Existing urls and in-flight ids
    // are read from refs, so storing a fetched preview must NOT re-fire this
    // effect — doing so cancels the in-flight batch after the first fetch and
    // leaves the rest of the QR codes stuck loading. (Previously this listed
    // `previewUrls`, which is exactly that bug.)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Persist a ticket's note and reflect it locally. Updating `tickets` here is
  // safe: the preview effect re-runs but finds every id already cached, so no
  // QR is re-fetched.
  async function onSaveNotes(ticketId: string, notes: string) {
    const updated = await updateTicketNotes(ticketId, notes);
    setTickets((prev) =>
      prev.map((t) => (t.id === ticketId ? { ...t, notes: updated.notes } : t))
    );
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
      <h1 className="text-2xl font-bold text-gray-900">Tickets — {raffleName}</h1>
      <p className="mb-6 text-sm text-gray-500">
        Each ticket shows the legal raffle details, your logos, and a QR the
        seller scans at the point of sale. Download the A4 PDF (6 per page) to
        print in bulk.
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
        <LogoManager raffleId={raffleId} onChange={clearPreviews} />
      </div>

      <p className="mb-4 text-sm font-medium text-gray-600">
        {tickets.length} ticket{tickets.length === 1 ? "" : "s"} generated
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            qrUrl={previewUrls[t.id] ?? ""}
            onSaveNotes={onSaveNotes}
          />
        ))}
      </div>
    </div>
  );
}
