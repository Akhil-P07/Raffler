import type { Ticket } from "../api/types";

interface Props {
  ticket: Ticket;
  previewUrl: string; // object URL of the full 10:11 ticket preview, or ""
}

/**
 * Shows a single ticket exactly as it will print (the server-rendered 10:11
 * design, including logos and the tear-off stub), with a registered badge.
 */
export default function TicketCard({ ticket, previewUrl }: Props) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-gray-300 bg-white shadow-sm">
      <span
        className={`absolute right-1 top-1 z-10 rounded-full px-2 py-0.5 text-xs font-semibold ${
          ticket.registered
            ? "bg-green-100 text-green-700"
            : "bg-gray-100 text-gray-500"
        }`}
      >
        {ticket.registered ? "Registered" : "#" + ticket.ticket_number}
      </span>
      {previewUrl ? (
        <img
          src={previewUrl}
          alt={`Ticket ${ticket.ticket_number} preview`}
          className="block w-full"
          loading="lazy"
        />
      ) : (
        // 10:11 placeholder to avoid layout shift while the preview loads.
        <div
          className="w-full animate-pulse bg-gray-100"
          style={{ aspectRatio: "10 / 11" }}
          aria-label="Loading ticket preview"
        />
      )}
    </div>
  );
}
