import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage, getMe, updateOrg } from "../api/client";

/** Edit the organization name + Games-of-Chance ID printed on tickets. */
export default function OrgSettings() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [gocId, setGocId] = useState("");
  const [plan, setPlan] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then((me) => {
        setName(me.org.name);
        setGocId(me.org.goc_id ?? "");
        setPlan(me.org.plan);
        setLoaded(true);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await updateOrg({ name, goc_id: gocId.trim() || null });
      setMsg("Saved.");
    } catch (err) {
      setError(errorMessage(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  }

  const field =
    "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 text-sm text-gray-500 hover:text-brand"
      >
        ← Back to dashboard
      </button>
      <h1 className="mb-1 text-2xl font-bold text-gray-900">Organization settings</h1>
      <p className="mb-4 text-sm text-gray-500">
        Plan: <span className="font-medium capitalize">{plan || "…"}</span>. The
        name and Games-of-Chance ID are printed on your tickets.
      </p>
      <form onSubmit={onSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow">
        <div>
          <label htmlFor="org-name" className="block text-sm font-medium text-gray-700">
            Organization name
          </label>
          <input
            id="org-name"
            type="text"
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={field}
            disabled={!loaded}
          />
        </div>
        <div>
          <label htmlFor="goc" className="block text-sm font-medium text-gray-700">
            Games-of-Chance ID (optional)
          </label>
          <input
            id="goc"
            type="text"
            maxLength={60}
            value={gocId}
            onChange={(e) => setGocId(e.target.value)}
            placeholder="e.g. 12-345-6789-012345"
            className={field}
            disabled={!loaded}
          />
        </div>
        <p role="status" aria-live="polite" className="text-sm text-green-600">
          {msg ?? ""}
        </p>
        <p role="alert" aria-live="assertive" className="text-sm text-red-600">
          {error ?? ""}
        </p>
        <button
          type="submit"
          disabled={busy || !loaded || !name.trim()}
          className="w-full rounded-lg bg-brand py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </form>
    </div>
  );
}
