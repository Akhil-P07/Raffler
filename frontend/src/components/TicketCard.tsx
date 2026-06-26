import { useEffect, useRef, useState } from "react";
import { fetchQrObjectUrl, ticketSerial } from "../api/client";
import type { Ticket } from "../api/types";

interface Props {
  ticket: Ticket;
  // The raffle's event code; serial renders as #<eventCode>-<number>.
  eventCode: string | null;
  // When true (parent's "Reveal all"), the card loads its QR once on its own.
  reveal: boolean;
}

/**
 * A single ticket: its serial (#<event-code>-<number>) and an on-demand QR.
 *
 * The QR (which encodes the unguessable registration token the org scans to
 * register a buyer) is fetched only when the user clicks "Show QR" or the page
 * triggers "Reveal all" — never automatically. Each QR is its own server-
 * rendered request, so loading lazily saves compute and stays within rate
 * limits on large raffles.
 */
export default function TicketCard({ ticket, eventCode, reveal }: Props) {
  const [qrUrl, setQrUrl] = useState("");
  const [qrLoading, setQrLoading] = useState(false);
  const [qrError, setQrError] = useState(false);
  // Guards against a second fetch once one has started/succeeded.
  const fetchedRef = useRef(false);

  async function loadQr() {
    if (fetchedRef.current || qrLoading) return;
    fetchedRef.current = true;
    setQrLoading(true);
    setQrError(false);
    try {
      setQrUrl(await fetchQrObjectUrl(ticket.id));
    } catch {
      setQrError(true);
      fetchedRef.current = false; // allow a retry
    } finally {
      setQrLoading(false);
    }
  }

  // Load once when the parent flips "Reveal all" on.
  useEffect(() => {
    if (reveal) loadQr();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal]);

  // Revoke the object URL when it changes or on unmount.
  useEffect(() => {
    return () => {
      if (qrUrl) URL.revokeObjectURL(qrUrl);
    };
  }, [qrUrl]);

  const serial = ticketSerial(eventCode, ticket.ticket_number);

  return (
    <div className="flex flex-col items-center rounded-lg border border-gray-300 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
        Ticket
      </div>
      <div className="text-xl font-bold text-gray-900">{serial}</div>

      {qrUrl ? (
        <img
          src={qrUrl}
          alt={`QR code for ticket ${serial}`}
          className="my-2 h-36 w-36"
        />
      ) : (
        <div className="my-2 flex h-36 w-36 items-center justify-center rounded bg-gray-50">
          {qrLoading ? (
            <div
              className="h-full w-full animate-pulse rounded bg-gray-100"
              aria-label="Loading QR code"
            />
          ) : (
            <button
              type="button"
              onClick={loadQr}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
            >
              {qrError ? "Retry QR" : "Show QR"}
            </button>
          )}
        </div>
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
