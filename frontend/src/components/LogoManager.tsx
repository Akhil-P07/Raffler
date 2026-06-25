import { useEffect, useRef, useState } from "react";
import {
  deleteRaffleLogo,
  errorMessage,
  fetchRaffleLogoUrl,
  listRaffleLogos,
  uploadRaffleLogo,
} from "../api/client";
import type { RaffleLogo } from "../api/types";

interface Props {
  raffleId: string;
  /** Called after a logo is added/removed so ticket previews can refresh. */
  onChange?: () => void;
}

/**
 * Manage the logos printed on a raffle's tickets. A raffle can be co-hosted by
 * several organizations, so multiple logos are supported. SVGs are rasterized
 * to PNG in the browser before upload.
 */
export default function LogoManager({ raffleId, onChange }: Props) {
  const [logos, setLogos] = useState<RaffleLogo[]>([]);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const previewsRef = useRef<Record<string, string>>({});
  previewsRef.current = previews;

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setLogos(await listRaffleLogos(raffleId));
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
    return () => {
      Object.values(previewsRef.current).forEach(URL.revokeObjectURL);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raffleId]);

  // Load a preview object URL for any logo that doesn't have one yet. Reads
  // existing previews from the ref so storing one doesn't re-fire the effect
  // (avoids the re-render churn the QR effect also guards against).
  useEffect(() => {
    let cancelled = false;
    const missing = logos.filter((l) => !previewsRef.current[l.id]);
    if (missing.length === 0) return;
    (async () => {
      for (const l of missing) {
        try {
          const url = await fetchRaffleLogoUrl(raffleId, l.id);
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          setPreviews((p) => ({ ...p, [l.id]: url }));
        } catch {
          /* skip preview on failure */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [logos, raffleId]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      await uploadRaffleLogo(raffleId, file, name);
      setName("");
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
      onChange?.();
    } catch (err) {
      setError(errorMessage(err, "Could not upload logo."));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(id: string) {
    if (removingId) return;
    setRemovingId(id);
    setError(null);
    try {
      await deleteRaffleLogo(raffleId, id);
      const url = previews[id];
      if (url) URL.revokeObjectURL(url);
      setPreviews((p) => {
        const { [id]: _drop, ...rest } = p;
        return rest;
      });
      await refresh();
      onChange?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="rounded-xl bg-white p-4 shadow">
      <h2 className="font-semibold text-gray-900">Organization logos</h2>
      <p className="mb-3 text-sm text-gray-500">
        Printed across the top of each ticket. Add one per co-hosting
        organization. PNG, JPG, or SVG (SVGs are converted automatically).
      </p>

      {logos.length > 0 && (
        <ul className="mb-4 flex flex-wrap gap-3">
          {logos.map((l) => (
            <li
              key={l.id}
              className="flex flex-col items-center rounded-lg border border-gray-200 p-2"
            >
              {previews[l.id] ? (
                <img
                  src={previews[l.id]}
                  alt={l.name ?? "Logo"}
                  className="h-12 w-auto max-w-[120px] object-contain"
                />
              ) : (
                <div className="h-12 w-16 animate-pulse rounded bg-gray-100" />
              )}
              {l.name && (
                <span className="mt-1 max-w-[120px] truncate text-xs text-gray-600">
                  {l.name}
                </span>
              )}
              <button
                type="button"
                onClick={() => onRemove(l.id)}
                disabled={removingId === l.id}
                className="mt-1 text-xs text-red-600 hover:underline disabled:opacity-50"
              >
                {removingId === l.id ? "Removing…" : "Remove"}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={onUpload} className="flex flex-wrap items-end gap-3">
        <div>
          <label
            htmlFor="logo-file"
            className="block text-sm font-medium text-gray-700"
          >
            Logo file
          </label>
          <input
            id="logo-file"
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
            className="mt-1 block w-full text-sm text-gray-500 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-brand/10 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-brand-dark hover:file:bg-brand/20"
          />
        </div>
        <div>
          <label
            htmlFor="logo-name"
            className="block text-sm font-medium text-gray-700"
          >
            Label (optional)
          </label>
          <input
            id="logo-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Co-host org name"
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Uploading…" : "Add logo"}
        </button>
      </form>
      <p role="alert" aria-live="assertive" className="mt-2 text-sm text-red-600">
        {error ?? ""}
      </p>
    </div>
  );
}
