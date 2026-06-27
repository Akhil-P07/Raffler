import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import EntryTable from "../components/EntryTable";
import {
  deregisterEntries,
  downloadEntriesCsv,
  errorMessage,
  getRaffle,
  listEntries,
} from "../api/client";
import { isOwner, useMe } from "../auth/MeContext";
import type { Entry, RaffleDetail } from "../api/types";

/** Entries for a single raffle on their own page (like the tickets page).
 *  Lists registrations, exports the CSV, and — for owners before the draw —
 *  allows deregistration. Polls so new registrations appear without a refresh. */
export default function EntriesPage() {
  const { raffleId = "" } = useParams();
  const navigate = useNavigate();
  const { me } = useMe();
  const owner = isOwner(me);

  const [detail, setDetail] = useState<RaffleDetail | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [d, e] = await Promise.all([
      getRaffle(raffleId),
      listEntries(raffleId),
    ]);
    setDetail(d);
    setEntries(e);
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raffleId]);

  // Live-refresh while open so registrations from sellers' devices appear
  // without a manual tab refresh. EntryTable keeps its own selection/search.
  useEffect(() => {
    if (!raffleId) return;
    const id = setInterval(() => {
      listEntries(raffleId).then(setEntries).catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, [raffleId]);

  async function onDeregister(entryIds: string[]) {
    try {
      await deregisterEntries(raffleId, entryIds);
      await refresh();
    } catch (err) {
      setError(errorMessage(err, "Could not deregister."));
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 text-sm text-gray-500 hover:text-brand"
      >
        ← Back to dashboard
      </button>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Entries{detail ? `: ${detail.name}` : ""}
          </h1>
          {detail && (
            <p className="text-sm text-gray-500">
              {detail.entry_count} entries · {detail.ticket_count} tickets ·
              status {detail.status}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() =>
            downloadEntriesCsv(raffleId, detail?.name || "raffle").catch((err) =>
              setError(errorMessage(err))
            )
          }
          disabled={entries.length === 0}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Export CSV
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="rounded-xl bg-white p-4 shadow">
        <EntryTable
          entries={entries}
          eventCode={detail?.event_code ?? null}
          selectable={owner && detail?.status !== "drawn"}
          onDeregister={onDeregister}
        />
      </div>
    </div>
  );
}
