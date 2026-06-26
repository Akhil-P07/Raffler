import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import EntryTable from "../components/EntryTable";
import WinnerModal from "../components/WinnerModal";
import {
  deleteRaffle,
  deregisterEntries,
  downloadEntriesCsv,
  drawRaffle,
  errorMessage,
  getRaffle,
  listEntries,
  listRaffles,
  listWinners,
  updateRaffle,
} from "../api/client";
import { isOwner, useMe } from "../auth/MeContext";
import type { Entry, Raffle, RaffleDetail, Winner } from "../api/types";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  closed: "bg-yellow-100 text-yellow-700",
  drawn: "bg-gray-200 text-gray-700",
};

export default function AdminDashboard() {
  const navigate = useNavigate();
  const { me } = useMe();
  const owner = isOwner(me);
  const [raffles, setRaffles] = useState<Raffle[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RaffleDetail | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [winners, setWinners] = useState<Winner[]>([]);
  const [prizeCount, setPrizeCount] = useState(1);
  const [showWinners, setShowWinners] = useState(false);
  const [alreadyDrawn, setAlreadyDrawn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Hard guard against a re-entrant draw (the draw is final and irreversible).
  const drawInFlight = useRef(false);
  const countdownInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clean up the countdown interval if the component unmounts mid-countdown.
  useEffect(() => () => {
    if (countdownInterval.current) clearInterval(countdownInterval.current);
  }, []);

  // Live-refresh the selected raffle's entries + counts while the page is open,
  // so registrations coming in from sellers' devices appear without a manual
  // tab refresh. EntryTable keeps its own selection/search/sort across updates.
  useEffect(() => {
    if (!selectedId) return;
    const id = setInterval(() => {
      // Don't disturb an in-progress draw or the countdown reveal.
      if (drawInFlight.current || countdown !== null) return;
      Promise.all([getRaffle(selectedId), listEntries(selectedId)])
        .then(([d, e]) => {
          setDetail(d);
          setEntries(e);
        })
        .catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, [selectedId, countdown]);

  async function loadRaffles() {
    setRaffles(await listRaffles());
  }

  useEffect(() => {
    loadRaffles().catch((err) => setError(errorMessage(err)));
  }, []);

  async function selectRaffle(id: string) {
    setSelectedId(id);
    setError(null);
    try {
      const [d, e, w] = await Promise.all([
        getRaffle(id),
        listEntries(id),
        listWinners(id),
      ]);
      setDetail(d);
      setEntries(e);
      setWinners(w);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function onDraw() {
    if (!detail || busy || drawInFlight.current) return;
    if (
      !window.confirm(
        "Draw is final and cannot be undone. Make sure you've exported the entries CSV first. Continue?"
      )
    )
      return;
    drawInFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await drawRaffle(detail.id, prizeCount);
      setWinners(res.winners);
      setAlreadyDrawn(res.already_drawn);

      // Kick off sidebar/header refresh in the background — these don't block the reveal.
      Promise.all([selectRaffle(detail.id), loadRaffles()]).catch(() => {});

      if (res.already_drawn) {
        // Re-viewing a previously recorded draw: skip the countdown.
        setShowWinners(true);
        setBusy(false);
        drawInFlight.current = false;
      } else {
        // Fresh draw: 3 → 2 → 1 countdown, then reveal.
        setCountdown(3);
        let n = 3;
        countdownInterval.current = setInterval(() => {
          n -= 1;
          if (n <= 0) {
            clearInterval(countdownInterval.current!);
            countdownInterval.current = null;
            setCountdown(null);
            setShowWinners(true);
            setBusy(false);
            drawInFlight.current = false;
          } else {
            setCountdown(n);
          }
        }, 1000);
      }
    } catch (err) {
      setError(errorMessage(err, "Could not run the draw."));
      setCountdown(null);
      if (countdownInterval.current) {
        clearInterval(countdownInterval.current);
        countdownInterval.current = null;
      }
      setBusy(false);
      drawInFlight.current = false;
    }
  }

  async function onClose() {
    if (!detail) return;
    try {
      await updateRaffle(detail.id, { status: "closed" });
      await Promise.all([selectRaffle(detail.id), loadRaffles()]);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function onDeregister(entryIds: string[]) {
    if (!detail) return;
    try {
      await deregisterEntries(detail.id, entryIds);
      await Promise.all([selectRaffle(detail.id), loadRaffles()]);
    } catch (err) {
      setError(errorMessage(err, "Could not deregister."));
    }
  }

  async function onDelete() {
    if (!detail) return;
    if (
      !window.confirm(
        "Soft-delete this raffle? Entries are preserved but it will be hidden. Export the CSV first if you need it."
      )
    )
      return;
    try {
      await deleteRaffle(detail.id);
      setSelectedId(null);
      setDetail(null);
      await loadRaffles();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Raffles</h1>
        {owner && (
          <button
            type="button"
            onClick={() => navigate("/raffles/new")}
            className="rounded-lg bg-brand px-4 py-2 font-semibold text-white hover:bg-brand-dark"
          >
            + New raffle
          </button>
        )}
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="grid gap-6 md:grid-cols-[18rem_1fr]">
        {/* Raffle list */}
        <aside className="space-y-2">
          {raffles.length === 0 && (
            <p className="text-sm text-gray-500">
              No raffles yet. Create one to get started.
            </p>
          )}
          {raffles.map((r) => (
            <button
              type="button"
              key={r.id}
              onClick={() => selectRaffle(r.id)}
              className={`block w-full rounded-lg border p-3 text-left transition ${
                selectedId === r.id
                  ? "border-brand bg-brand/5"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-gray-900">
                  {r.name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    STATUS_STYLES[r.status] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {r.status}
                </span>
              </div>
            </button>
          ))}
        </aside>

        {/* Detail */}
        <section>
          {!detail && (
            <p className="text-sm text-gray-500">
              Select a raffle to view its entries and run the draw.
            </p>
          )}
          {detail && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-4 shadow">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">
                    {detail.name}
                  </h2>
                  <p className="text-sm text-gray-500">
                    {detail.entry_count} entries · {detail.ticket_count} tickets
                    · status {detail.status}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {owner && (
                    <button
                      type="button"
                      onClick={() => navigate(`/raffles/${detail.id}/tickets`)}
                      className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                    >
                      Tickets
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      downloadEntriesCsv(detail.id, detail.name).catch((err) =>
                        setError(errorMessage(err))
                      )
                    }
                    disabled={detail.entry_count === 0}
                    className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Export CSV
                  </button>
                  {owner &&
                    detail.status !== "drawn" &&
                    winners.length === 0 && (
                      <button
                        type="button"
                        onClick={onClose}
                        disabled={detail.status === "closed"}
                        className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        Close
                      </button>
                    )}
                  {owner && (
                    <button
                      type="button"
                      onClick={onDelete}
                      className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-semibold text-red-600 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>

              {/* Draw / winners panel */}
              <div className="rounded-xl bg-white p-4 shadow">
                {detail.status === "drawn" || winners.length > 0 ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        Winner{winners.length > 1 ? "s" : ""} drawn
                      </h3>
                      <p className="text-sm text-gray-500">
                        This raffle has been drawn. The result is final.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setAlreadyDrawn(true);
                        setShowWinners(true);
                      }}
                      className="rounded-lg bg-brand px-4 py-2 font-semibold text-white hover:bg-brand-dark"
                    >
                      View winners
                    </button>
                  </div>
                ) : owner ? (
                  <div className="flex flex-wrap items-end gap-3">
                    <div>
                      <label
                        htmlFor="prizes"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Number of prizes
                      </label>
                      <input
                        id="prizes"
                        type="number"
                        min={1}
                        max={100}
                        value={prizeCount}
                        onChange={(e) => setPrizeCount(Number(e.target.value))}
                        className="mt-1 w-24 rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={onDraw}
                      disabled={busy || detail.entry_count === 0}
                      className="rounded-lg bg-brand px-6 py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
                      title={
                        detail.entry_count === 0
                          ? "No entries to draw from"
                          : undefined
                      }
                    >
                      {busy ? "Drawing…" : "Draw winner"}
                    </button>
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">
                    Not yet drawn. Only an owner can run the draw.
                  </p>
                )}
              </div>

              {/* Entries */}
              <div className="rounded-xl bg-white p-4 shadow">
                <h3 className="mb-3 font-semibold text-gray-900">Entries</h3>
                <EntryTable
                  entries={entries}
                  eventCode={detail.event_code}
                  selectable={owner && detail.status !== "drawn"}
                  onDeregister={onDeregister}
                />
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Countdown overlay — shown between draw API response and winner modal */}
      {countdown !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          aria-live="assertive"
          aria-label={`Drawing in ${countdown}`}
        >
          <span
            key={countdown}
            className="select-none font-bold text-white"
            style={{ fontSize: "14rem", lineHeight: 1, animation: "countdownPop 0.9s ease-out forwards" }}
          >
            {countdown}
          </span>
        </div>
      )}

      {showWinners && (
        <WinnerModal
          winners={winners}
          eventCode={detail?.event_code ?? null}
          alreadyDrawn={alreadyDrawn}
          onClose={() => setShowWinners(false)}
        />
      )}
    </div>
  );
}
