import { useEffect, useRef } from "react";
import type { Winner } from "../api/types";

interface Props {
  winners: Winner[];
  alreadyDrawn: boolean;
  onClose: () => void;
}

/** Overlay announcing the drawn winner(s). The draw is final and recorded. */
export default function WinnerModal({ winners, alreadyDrawn, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Move focus into the dialog on open so keyboard/screen-reader users land
  // inside it rather than behind the backdrop.
  useEffect(() => {
    closeRef.current?.focus();
  }, []);

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
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 text-center text-4xl">🎉</div>
        <h2
          id="winner-title"
          className="mb-4 text-center text-xl font-bold text-gray-900"
        >
          {winners.length > 1 ? "Winners" : "Winner"}
          {alreadyDrawn && (
            <span className="ml-2 align-middle text-xs font-normal text-gray-500">
              (already drawn)
            </span>
          )}
        </h2>

        <ul className="space-y-3">
          {winners.map((w) => (
            <li
              key={w.id}
              className="rounded-lg border border-brand/30 bg-brand/5 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-gray-900">{w.name}</span>
                {winners.length > 1 && (
                  <span className="text-xs font-medium text-brand-dark">
                    Prize #{w.prize_rank}
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-600">
                Ticket #{w.ticket_number} · {w.email}
              </div>
            </li>
          ))}
        </ul>

        <p className="mt-4 text-center text-xs text-gray-500">
          Contact the winner using the email above. This result is final and
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
