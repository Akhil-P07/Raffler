import { useEffect, useState } from "react";
import type { Ticket } from "../api/types";

interface Props {
  ticket: Ticket;
  qrUrl: string; // object URL of the ticket's QR PNG, or ""
  // Persist a notes edit; resolves once saved (parent updates the ticket).
  onSaveNotes: (ticketId: string, notes: string) => Promise<void>;
}

/**
 * A single ticket: its number, QR code (the QR encodes the unguessable
 * registration token — the org scans it to register the buyer), and an
 * editable free-text note for per-ticket unique info. Notes save on blur.
 */
export default function TicketCard({ ticket, qrUrl, onSaveNotes }: Props) {
  const [notes, setNotes] = useState(ticket.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failed, setFailed] = useState(false);

  // Re-sync when the ticket's stored note changes (e.g. after a page refresh).
  useEffect(() => {
    setNotes(ticket.notes ?? "");
  }, [ticket.notes]);

  const dirty = notes.trim() !== (ticket.notes ?? "");

  async function save() {
    if (!dirty || saving) return;
    setSaving(true);
    setSaved(false);
    setFailed(false);
    try {
      await onSaveNotes(ticket.id, notes.trim());
      setSaved(true);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col items-center rounded-lg border border-gray-300 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
        Ticket
      </div>
      <div className="text-2xl font-bold text-gray-900">#{ticket.ticket_number}</div>
      {qrUrl ? (
        <img
          src={qrUrl}
          alt={`QR code for ticket ${ticket.ticket_number}`}
          className="my-2 h-36 w-36"
          loading="lazy"
        />
      ) : (
        <div
          className="my-2 h-36 w-36 animate-pulse rounded bg-gray-100"
          aria-label="Loading QR code"
        />
      )}
      <div
        className={`text-xs font-medium ${
          ticket.registered ? "text-green-600" : "text-gray-400"
        }`}
      >
        {ticket.registered ? "Registered" : "Unregistered"}
      </div>

      <div className="mt-3 w-full">
        <label
          htmlFor={`notes-${ticket.id}`}
          className="mb-1 block text-xs font-medium text-gray-600"
        >
          Notes
        </label>
        <textarea
          id={`notes-${ticket.id}`}
          value={notes}
          onChange={(e) => {
            setNotes(e.target.value);
            setSaved(false);
            setFailed(false);
          }}
          onBlur={save}
          rows={2}
          maxLength={500}
          placeholder="Unique info (seat, table, …)"
          className="w-full resize-y rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <div className="h-4 text-xs" aria-live="polite">
          {saving ? (
            <span className="text-gray-400">Saving…</span>
          ) : failed ? (
            <span className="text-red-600">Couldn’t save — try again.</span>
          ) : dirty ? (
            <span className="text-gray-400">Unsaved</span>
          ) : saved ? (
            <span className="text-green-600">Saved</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
