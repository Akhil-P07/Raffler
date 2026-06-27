import { useEffect, useState } from "react";
import {
  errorMessage,
  inviteMember,
  listMembers,
  removeMember,
} from "../api/client";
import type { OrgMember } from "../api/types";

/** Owner-only: list members + pending invites, invite by email, remove. */
export default function MembersManager() {
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setMembers(await listMembers());
  }

  useEffect(() => {
    refresh().catch((err) => setError(errorMessage(err)));
  }, []);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !email.trim()) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await inviteMember(email.trim());
      setMsg(`Invitation sent to ${email.trim()}.`);
      setEmail("");
      await refresh();
    } catch (err) {
      setError(errorMessage(err, "Could not send the invitation."));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(memberEmail: string) {
    if (!window.confirm(`Remove ${memberEmail} from this organization?`)) return;
    setError(null);
    try {
      await removeMember(memberEmail);
      await refresh();
    } catch (err) {
      setError(errorMessage(err, "Could not remove that member."));
    }
  }

  const badge: Record<string, string> = {
    owner: "bg-brand/10 text-brand-dark",
    member: "bg-gray-100 text-gray-600",
    invited: "bg-yellow-100 text-yellow-700",
  };

  return (
    <div className="rounded-xl bg-white p-6 shadow">
      <h2 className="font-semibold text-gray-900">Team members</h2>
      <p className="mb-3 text-sm text-gray-500">
        Invite people by email. They get a link to set a password and join.
        Members can register tickets at the point of sale but can't see or print
        QR codes.
      </p>

      <ul className="mb-4 divide-y divide-gray-100">
        {members.map((m) => (
          <li key={m.email} className="flex items-center justify-between py-2">
            <span className="text-sm text-gray-800">{m.email}</span>
            <span className="flex items-center gap-3">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  badge[m.status] ?? "bg-gray-100 text-gray-600"
                }`}
              >
                {m.status}
              </span>
              {m.status !== "owner" && (
                <button
                  type="button"
                  onClick={() => onRemove(m.email)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Remove
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      <form onSubmit={onInvite} className="flex flex-wrap items-end gap-3">
        <div className="flex-1">
          <label
            htmlFor="member-email"
            className="block text-sm font-medium text-gray-700"
          >
            Invite by email
          </label>
          <input
            id="member-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@club.org"
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !email.trim()}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Sending…" : "Send invite"}
        </button>
      </form>
      {msg && <p className="mt-2 text-sm text-green-600">{msg}</p>}
      <p role="alert" aria-live="assertive" className="mt-2 text-sm text-red-600">
        {error ?? ""}
      </p>
    </div>
  );
}
