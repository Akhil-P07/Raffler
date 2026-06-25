import { useMemo, useState } from "react";
import type { Entry } from "../api/types";

type SortKey = "ticket_number" | "name" | "registered_at";

interface Props {
  entries: Entry[];
  /** Owners only: enables checkboxes + a "Deregister selected" action. */
  selectable?: boolean;
  onDeregister?: (entryIds: string[]) => Promise<void> | void;
}

/** Sortable list of entries; optionally selectable for owner deregistration. */
export default function EntryTable({ entries, selectable, onDeregister }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("ticket_number");
  const [asc, setAsc] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [working, setWorking] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...entries];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "ticket_number") cmp = a.ticket_number - b.ticket_number;
      else if (sortKey === "name") cmp = a.name.localeCompare(b.name);
      else cmp = a.registered_at.localeCompare(b.registered_at);
      return asc ? cmp : -cmp;
    });
    return copy;
  }, [entries, sortKey, asc]);

  function toggle(key: SortKey) {
    if (key === sortKey) setAsc((v) => !v);
    else {
      setSortKey(key);
      setAsc(true);
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) =>
      prev.size === entries.length ? new Set() : new Set(entries.map((e) => e.id))
    );
  }

  async function deregister() {
    if (!onDeregister || selected.size === 0 || working) return;
    if (
      !window.confirm(
        `Deregister ${selected.size} ticket(s)? Their entries are removed and the tickets can be registered again.`
      )
    )
      return;
    setWorking(true);
    try {
      await onDeregister([...selected]);
      setSelected(new Set());
    } finally {
      setWorking(false);
    }
  }

  const arrow = (key: SortKey) => (key === sortKey ? (asc ? " ▲" : " ▼") : "");
  const ariaSort = (key: SortKey): "ascending" | "descending" | "none" =>
    key === sortKey ? (asc ? "ascending" : "descending") : "none";

  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        No entries yet. Sellers register buyers by scanning a ticket's QR.
      </p>
    );
  }

  return (
    <div>
      {selectable && (
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {selected.size} selected
          </span>
          <button
            type="button"
            onClick={deregister}
            disabled={selected.size === 0 || working}
            className="rounded-lg border border-red-200 px-3 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            {working ? "Deregistering…" : "Deregister selected"}
          </button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead>
            <tr className="text-left text-gray-600">
              {selectable && (
                <th className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label="Select all entries"
                    checked={selected.size === entries.length}
                    onChange={toggleAll}
                  />
                </th>
              )}
              <th className="px-3 py-2" aria-sort={ariaSort("ticket_number")}>
                <button
                  type="button"
                  className="font-semibold hover:text-brand"
                  onClick={() => toggle("ticket_number")}
                >
                  Ticket #<span aria-hidden="true">{arrow("ticket_number")}</span>
                </button>
              </th>
              <th className="px-3 py-2" aria-sort={ariaSort("name")}>
                <button
                  type="button"
                  className="font-semibold hover:text-brand"
                  onClick={() => toggle("name")}
                >
                  Name<span aria-hidden="true">{arrow("name")}</span>
                </button>
              </th>
              <th className="px-3 py-2 font-semibold">Email</th>
              <th className="px-3 py-2" aria-sort={ariaSort("registered_at")}>
                <button
                  type="button"
                  className="font-semibold hover:text-brand"
                  onClick={() => toggle("registered_at")}
                >
                  Registered
                  <span aria-hidden="true">{arrow("registered_at")}</span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((e) => (
              <tr key={e.id} className="text-gray-800">
                {selectable && (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ticket ${e.ticket_number}`}
                      checked={selected.has(e.id)}
                      onChange={() => toggleOne(e.id)}
                    />
                  </td>
                )}
                <td className="px-3 py-2 font-mono">#{e.ticket_number}</td>
                <td className="px-3 py-2">{e.name}</td>
                <td className="px-3 py-2 text-gray-600">{e.email}</td>
                <td className="px-3 py-2 text-gray-500">
                  {new Date(e.registered_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
