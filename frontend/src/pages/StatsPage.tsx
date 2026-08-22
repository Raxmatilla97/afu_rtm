import { useEffect, useState } from "react";
import { statsApi } from "@/api/reference";
import type { MonthlyCount, StatsSummary } from "@/types";

export function StatsPage() {
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [monthly, setMonthly] = useState<MonthlyCount[]>([]);

  useEffect(() => {
    statsApi.summary().then(setSummary);
    statsApi.completedByMonth().then(setMonthly);
  }, []);

  const maxCount = Math.max(1, ...monthly.map((m) => m.count));

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Statistika</h1>

      {summary && (
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["Jami", summary.total_requests],
            ["Yangi", summary.new_count],
            ["Tayinlangan", summary.assigned_count],
            ["Jarayonda", summary.in_progress_count],
            ["Bajarilgan", summary.completed_count],
            ["Bekor qilingan", summary.cancelled_count],
          ].map(([label, value]) => (
            <div key={label as string} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-2xl font-bold text-brand-700">{value}</div>
              <div className="text-xs text-slate-500">{label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="mb-4 font-medium text-slate-800">Oylar kesimida bajarilgan murojaatlar</div>
        {monthly.length === 0 ? (
          <div className="text-sm text-slate-400">Ma'lumot yo'q</div>
        ) : (
          <div className="flex items-end gap-3" style={{ height: 160 }}>
            {monthly.map((m) => (
              <div key={m.month} className="flex flex-1 flex-col items-center gap-2">
                <div className="text-xs font-medium text-slate-600">{m.count}</div>
                <div
                  className="w-full rounded-t bg-brand-500"
                  style={{ height: `${(m.count / maxCount) * 120}px` }}
                />
                <div className="text-xs text-slate-400">{m.month}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
