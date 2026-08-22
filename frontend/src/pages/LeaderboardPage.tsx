import { useEffect, useState } from "react";
import { ratingsApi } from "@/api/reference";
import type { StaffRatingSummary } from "@/types";

const MEDALS = ["🥇", "🥈", "🥉"];

export function LeaderboardPage() {
  const [items, setItems] = useState<StaffRatingSummary[]>([]);

  useEffect(() => {
    ratingsApi.leaderboard().then(setItems);
  }, []);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold text-slate-900">Top RTM xodimlari</h1>
      <p className="mb-6 text-sm text-slate-500">Reyting va bajarilgan murojaatlar soni bo'yicha</p>

      <div className="space-y-3">
        {items.map((s, idx) => (
          <div
            key={s.employee_id}
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4"
          >
            <div className="flex items-center gap-4">
              <div className="w-8 text-center text-xl">{MEDALS[idx] || idx + 1}</div>
              <div>
                <div className="font-medium text-slate-900">{s.full_name}</div>
                <div className="text-xs text-slate-500">{s.completed_count} ta murojaat bajarilgan</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-lg font-bold text-amber-500">
                {s.average_score !== null ? `★ ${s.average_score}` : "—"}
              </div>
              <div className="text-xs text-slate-400">{s.rating_count} ta baho</div>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-400">
            Hozircha ma'lumot yo'q
          </div>
        )}
      </div>
    </div>
  );
}
