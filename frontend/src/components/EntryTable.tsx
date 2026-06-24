import { useMemo, useState } from "react";
import type { Entry } from "../api/types";

type SortKey = "ticket_number" | "name" | "registered_at";

interface Props {
  entries: Entry[];
}

/** Sortable list of entries: ticket number, name, email, registered time. */
export default function EntryTable({ entries }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("ticket_number");
  const [asc, setAsc] = useState(true);

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

  const arrow = (key: SortKey) => (key === sortKey ? (asc ? " ▲" : " ▼") : "");

  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        No entries yet. Buyers register by scanning their ticket's QR code.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead>
          <tr className="text-left text-gray-600">
            <th className="px-3 py-2">
              <button
                type="button"
                className="font-semibold hover:text-brand"
                onClick={() => toggle("ticket_number")}
              >
                Ticket #{arrow("ticket_number")}
              </button>
            </th>
            <th className="px-3 py-2">
              <button
                type="button"
                className="font-semibold hover:text-brand"
                onClick={() => toggle("name")}
              >
                Name{arrow("name")}
              </button>
            </th>
            <th className="px-3 py-2 font-semibold">Email</th>
            <th className="px-3 py-2">
              <button
                type="button"
                className="font-semibold hover:text-brand"
                onClick={() => toggle("registered_at")}
              >
                Registered{arrow("registered_at")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((e) => (
            <tr key={e.id} className="text-gray-800">
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
  );
}
