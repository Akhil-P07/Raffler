import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createRaffle, errorMessage } from "../api/client";

export default function CreateRaffle() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [prizes, setPrizes] = useState("");
  const [drawingAt, setDrawingAt] = useState(""); // datetime-local
  const [location, setLocation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const raffle = await createRaffle({
        name,
        ticket_price: price || undefined,
        prizes: prizes || undefined,
        // datetime-local yields a tz-less "YYYY-MM-DDTHH:MM". Send it verbatim
        // (NOT toISOString, which would shift to UTC) so the time printed on
        // the ticket matches exactly what the admin typed for the local event.
        drawing_datetime: drawingAt ? `${drawingAt}:00` : undefined,
        drawing_location: location || undefined,
      });
      // Send the admin straight to generating tickets for the new raffle.
      navigate(`/raffles/${raffle.id}/tickets`);
    } catch (err) {
      setError(errorMessage(err, "Could not create raffle."));
      setSubmitting(false);
    }
  }

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";
  const labelCls = "block text-sm font-medium text-gray-700";

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 text-sm text-gray-500 hover:text-brand"
      >
        ← Back to dashboard
      </button>
      <h1 className="mb-1 text-2xl font-bold text-gray-900">New raffle</h1>
      <p className="mb-4 text-sm text-gray-500">
        Prize, price, and drawing details are printed on each ticket to meet
        RIT/NY raffle rules. They're optional here but required on the ticket
        face if you sell tickets in advance.
      </p>
      <form
        onSubmit={onSubmit}
        className="space-y-4 rounded-xl bg-white p-6 shadow"
      >
        <div>
          <label htmlFor="raffle-name" className={labelCls}>
            Raffle name
          </label>
          <input
            id="raffle-name"
            type="text"
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Spring 2026 Fundraiser"
            className={field}
          />
        </div>

        <div>
          <label htmlFor="prizes" className={labelCls}>
            Prize(s)
          </label>
          <input
            id="prizes"
            type="text"
            maxLength={500}
            value={prizes}
            onChange={(e) => setPrizes(e.target.value)}
            placeholder="e.g. Dinner for Two at Delmonte Lodge"
            className={field}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="price" className={labelCls}>
              Ticket price
            </label>
            <input
              id="price"
              type="text"
              maxLength={20}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="e.g. 5.00"
              className={field}
            />
          </div>
          <div>
            <label htmlFor="drawing-at" className={labelCls}>
              Drawing date &amp; time
            </label>
            <input
              id="drawing-at"
              type="datetime-local"
              value={drawingAt}
              onChange={(e) => setDrawingAt(e.target.value)}
              className={field}
            />
          </div>
        </div>

        <div>
          <label htmlFor="location" className={labelCls}>
            Drawing location
          </label>
          <input
            id="location"
            type="text"
            maxLength={200}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Fireside Lounge"
            className={field}
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting || !name.trim()}
          className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {submitting ? "Creating…" : "Create raffle"}
        </button>
      </form>
    </div>
  );
}
