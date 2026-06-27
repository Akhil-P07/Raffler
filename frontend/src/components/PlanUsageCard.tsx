import type { PlanUsage } from "../api/types";

interface Props {
  usage: PlanUsage;
}

function barColor(pct: number): string {
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80) return "bg-amber-500";
  return "bg-brand";
}

/** Visual tracker of the org's plan usage vs. limits (settings page). */
export default function PlanUsageCard({ usage }: Props) {
  const isClub = usage.plan === "club";
  const rLimit = usage.lifetime_raffles_limit;
  const rUsed = usage.lifetime_raffles_used;
  const rPct = rLimit === null ? 0 : Math.min(100, (rUsed / rLimit) * 100);
  const rafflesMaxed = rLimit !== null && rUsed >= rLimit;

  return (
    <div className="mb-6 rounded-xl bg-white p-6 shadow">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Plan &amp; usage</h2>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            isClub ? "bg-brand/10 text-brand-dark" : "bg-gray-100 text-gray-600"
          }`}
        >
          {isClub ? "Club" : "Free"}
        </span>
      </div>

      {/* Raffles (lifetime) */}
      <div className="mb-4">
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="font-medium text-gray-700">
            Raffles created (lifetime)
          </span>
          <span className="text-gray-500">
            {rLimit === null
              ? `${rUsed} · Unlimited`
              : `${rUsed} / ${rLimit}`}
          </span>
        </div>
        {rLimit === null ? (
          <div className="h-2 w-full rounded-full bg-brand/20" />
        ) : (
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className={`h-full rounded-full transition-all ${barColor(rPct)}`}
              style={{ width: `${Math.max(rPct, 3)}%` }}
            />
          </div>
        )}
      </div>

      {/* Tickets per raffle (a per-raffle cap, not a single running total) */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-gray-700">Tickets per raffle</span>
        <span className="text-gray-500">
          {usage.tickets_per_raffle_limit === null
            ? "Unlimited"
            : `Up to ${usage.tickets_per_raffle_limit}`}
        </span>
      </div>

      {!isClub && (
        <p
          className={`mt-4 rounded-lg px-3 py-2 text-xs ${
            rafflesMaxed
              ? "bg-amber-50 text-amber-700"
              : "bg-gray-50 text-gray-500"
          }`}
        >
          {rafflesMaxed
            ? "You've used all your free raffles. Upgrade to Club for unlimited raffles and tickets."
            : "Free plan. Upgrade to Club for unlimited raffles and tickets."}
        </p>
      )}
    </div>
  );
}
