import type { Ticket } from "../api/types";

interface Props {
  ticket: Ticket;
  qrUrl: string; // object URL of the ticket's QR PNG, or ""
}

/**
 * A single ticket: its number and QR code (the QR encodes the unguessable
 * registration token — the seller scans it at point of sale).
 */
export default function TicketCard({ ticket, qrUrl }: Props) {
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
    </div>
  );
}
