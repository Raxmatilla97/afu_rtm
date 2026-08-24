import { Link } from "react-router-dom";
import type { RequestItem } from "@/types";

const OPEN = new Set(["new", "assigned", "in_progress"]);
const SOON_MS = 24 * 60 * 60 * 1000;

export function isOverdue(request: RequestItem, now = Date.now()): boolean {
  if (!request.deadline_at || !OPEN.has(request.status)) return false;
  return new Date(request.deadline_at).getTime() < now;
}

export function isDueSoon(request: RequestItem, now = Date.now()): boolean {
  if (!request.deadline_at || !OPEN.has(request.status)) return false;
  const left = new Date(request.deadline_at).getTime() - now;
  return left >= 0 && left < SOON_MS;
}

function lateBy(deadline: string, now = Date.now()): string {
  const minutes = Math.floor((now - new Date(deadline).getTime()) / 60000);
  if (minutes < 60) return `${minutes} daqiqa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} soat`;
  return `${Math.floor(hours / 24)} kun`;
}

/**
 * What the staff member sees before anything else on their home page.
 *
 * Placed above the counters on purpose. A late job is the only thing on this page that is
 * actually asking something of the reader; a tile saying "3 in progress" is not, and
 * putting them side by side would let the one that matters be read as decoration.
 */
export function OverdueAlert({ requests }: { requests: RequestItem[] }) {
  const overdue = requests.filter((r) => isOverdue(r));
  const soon = requests.filter((r) => isDueSoon(r));

  if (overdue.length === 0 && soon.length === 0) return null;

  return (
    <div className="mb-6 space-y-3">
      {overdue.length > 0 && (
        <section className="rounded-xl border border-red-300 bg-red-50 p-5" role="alert">
          <h2 className="mb-1 flex items-center gap-2 font-semibold text-red-800">
            <span className="text-lg">🔴</span>
            Muddati o'tgan topshiriqlar ({overdue.length})
          </h2>
          <p className="mb-3 text-sm text-red-700">
            Bu murojaatlar belgilangan muddatda bajarilmadi. Iltimos, zudlik bilan yakunlang
            yoki murojaatchiga holat haqida xabar bering.
          </p>
          <ul className="space-y-2">
            {overdue.map((r) => (
              <li key={r.id}>
                <Link
                  to={`/requests/${r.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2 text-sm hover:bg-red-100/50"
                >
                  <span className="font-medium text-slate-800">
                    {r.display_number} · {r.category_label}
                  </span>
                  <span className="font-semibold text-red-700">
                    {lateBy(r.deadline_at!)} kechikdi
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {soon.length > 0 && (
        <section className="rounded-xl border border-amber-300 bg-amber-50 p-5">
          <h2 className="mb-3 flex items-center gap-2 font-semibold text-amber-800">
            <span className="text-lg">⚠️</span>
            Muddati yaqinlashmoqda ({soon.length})
          </h2>
          <ul className="space-y-2">
            {soon.map((r) => (
              <li key={r.id}>
                <Link
                  to={`/requests/${r.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2 text-sm hover:bg-amber-100/50"
                >
                  <span className="font-medium text-slate-800">
                    {r.display_number} · {r.category_label}
                  </span>
                  <span className="text-amber-700">
                    {new Date(r.deadline_at!).toLocaleString("uz-UZ")}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
