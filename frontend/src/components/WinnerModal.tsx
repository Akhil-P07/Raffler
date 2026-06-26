import { useEffect, useRef, useState } from "react";
import Confetti from "./Confetti";
import { ticketSerial } from "../api/client";
import type { Winner } from "../api/types";

interface Props {
  winners: Winner[];
  // The raffle's event code; ticket serials render as #<eventCode>-<number>.
  eventCode: string | null;
  alreadyDrawn: boolean;
  onClose: () => void;
}

/** Overlay announcing the drawn winner(s). The draw is final and recorded.
 *  Ticket number and name show immediately; the email stays hidden until the
 *  user chooses to reveal it (per winner). */
export default function WinnerModal({
  winners,
  eventCode,
  alreadyDrawn,
  onClose,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  // Ids of winners whose email has been revealed by clicking "Show email".
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  // Move focus into the dialog on open so keyboard/screen-reader users land
  // inside it rather than behind the backdrop.
  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  function reveal(id: string) {
    setRevealed((prev) => new Set(prev).add(id));
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="winner-title"
      tabIndex={-1}
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl overflow-hidden"
        style={{ position: "relative", animation: "modalEnter 0.35s ease-out" }}
        onClick={(e) => e.stopPropagation()}
      >
        {!alreadyDrawn && <Confetti />}

        <div className="mb-1 text-center text-4xl">🎉</div>
        <h2
          id="winner-title"
          className="mb-4 text-center text-xl font-bold text-gray-900"
        >
          {winners.length > 1 ? "Winners" : "Winner"}
        </h2>

        <ul className="space-y-3">
          {winners.map((w, index) => (
            <li
              key={w.id}
              className="rounded-lg border border-brand/30 bg-brand/5 p-3"
              style={{
                animation: "modalEnter 0.3s ease-out both",
                animationDelay: `${0.15 + index * 0.1}s`,
              }}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-gray-900">{w.name}</span>
                {winners.length > 1 && (
                  <span className="text-xs font-medium text-brand-dark">
                    Prize #{w.prize_rank}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-sm text-gray-600">
                Ticket {ticketSerial(eventCode, w.ticket_number)}
              </div>
              <div className="mt-1 text-sm">
                {revealed.has(w.id) ? (
                  <span className="text-gray-600">{w.email}</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => reveal(w.id)}
                    className="font-medium text-brand hover:text-brand-dark"
                  >
                    Show email
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>

        <p className="mt-4 text-center text-xs text-gray-500">
          Reveal an email to contact the winner. This result is final and
          recorded.
        </p>

        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          className="mt-4 w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark"
        >
          Close
        </button>
      </div>
    </div>
  );
}
