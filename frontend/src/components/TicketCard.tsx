import type { Ticket } from "../api/types";

interface Props {
  ticket: Ticket;
  qrUrl: string; // authenticated QR PNG endpoint or an object URL
}

/**
 * A single print-ready ticket: human-readable number + its QR code. The QR
 * encodes the unguessable registration token, never the ticket number.
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
          className="my-2 h-32 w-32"
          loading="lazy"
        />
      ) : (
        // Avoid <img src=""> (broken-image icon + layout shift) while loading.
        <div
          className="my-2 h-32 w-32 animate-pulse rounded bg-gray-100"
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
