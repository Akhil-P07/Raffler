import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createRaffle, errorMessage } from "../api/client";

export default function CreateRaffle() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const raffle = await createRaffle(name);
      // Send the admin straight to generating tickets for the new raffle.
      navigate(`/raffles/${raffle.id}/tickets`);
    } catch (err) {
      setError(errorMessage(err, "Could not create raffle."));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 text-sm text-gray-500 hover:text-brand"
      >
        ← Back to dashboard
      </button>
      <h1 className="mb-4 text-2xl font-bold text-gray-900">New raffle</h1>
      <form
        onSubmit={onSubmit}
        className="space-y-4 rounded-xl bg-white p-6 shadow"
      >
        <div>
          <label
            htmlFor="raffle-name"
            className="block text-sm font-medium text-gray-700"
          >
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
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
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
