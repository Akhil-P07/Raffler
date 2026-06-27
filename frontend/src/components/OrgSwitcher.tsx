import { useEffect, useRef, useState } from "react";
import type { OrgMembershipSummary } from "../api/types";

interface Props {
  orgs: OrgMembershipSummary[];
  currentId: string;
  disabled?: boolean;
  onSwitch: (orgId: string) => void;
}

/** A compact custom dropdown for switching the active organization. Replaces
 *  the native <select> for a consistent, branded look across browsers. */
export default function OrgSwitcher({
  orgs,
  currentId,
  disabled,
  onSwitch,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = orgs.find((o) => o.id === currentId);

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch organization"
        onClick={() => setOpen((v) => !v)}
        className="flex max-w-[9rem] items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-800 transition hover:border-gray-400 hover:bg-gray-50 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-60 sm:max-w-[14rem]"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-4 w-4 shrink-0 text-brand"
        >
          <path d="M3 17V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v12h2V9a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v8h.5a.5.5 0 0 1 0 1H2.5a.5.5 0 0 1 0-1H3Zm3-9h2V6H6v2Zm0 4h2v-2H6v2Z" />
        </svg>
        <span className="truncate">{current?.name ?? "Organization"}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute right-0 z-50 mt-1 w-60 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
        >
          {orgs.map((o) => {
            const active = o.id === currentId;
            return (
              <button
                key={o.id}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  setOpen(false);
                  if (!active) onSwitch(o.id);
                }}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition hover:bg-gray-50 ${
                  active ? "bg-brand/5" : ""
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium text-gray-900">
                    {o.name}
                  </span>
                  <span className="block text-xs capitalize text-gray-400">
                    {o.role}
                    {o.plan === "club" ? " · Club" : ""}
                  </span>
                </span>
                {active && (
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className="h-4 w-4 shrink-0 text-brand"
                  >
                    <path
                      fillRule="evenodd"
                      d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0l-3.5-3.5a1 1 0 1 1 1.4-1.4l2.8 2.79 6.8-6.79a1 1 0 0 1 1.4 0Z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
