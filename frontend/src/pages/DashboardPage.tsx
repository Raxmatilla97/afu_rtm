import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { statsApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import { OverdueAlert } from "@/components/OverdueAlert";
import { useAuth } from "@/context/AuthContext";
import type { RequestItem, StatsSummary } from "@/types";

export function DashboardPage() {
  const { session } = useAuth();
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [mine, setMine] = useState<RequestItem[]>([]);

  const myEmployeeId = session.kind === "employee" ? session.employee.id : null;

  useEffect(() => {
    statsApi.summary().then(setSummary).catch(() => setSummary(null));
    // The list endpoint already scopes to what the caller may see, so this is "my work"
    // for a staff member and "my requests" for everyone else.
    requestsApi.list().then(setMine).catch(() => setMine([]));
  }, []);

  // Only jobs this person is actually on. A staff member's list also contains requests
  // they reported themselves, and being warned about a deadline somebody else owns would
  // train them to ignore the banner.
  const myWork =
    myEmployeeId === null
      ? mine
      : mine.filter((r) => r.assignees.some((a) => a.employee_id === myEmployeeId));

  const name = session.kind === "admin" ? session.admin.email : session.kind === "employee" ? session.employee.full_name : "";

  const cards = summary
    ? [
        { label: "Jami murojaatlar", value: summary.total_requests },
        { label: "Yangi", value: summary.new_count },
        { label: "Tayinlangan", value: summary.assigned_count },
        { label: "Jarayonda", value: summary.in_progress_count },
        { label: "Bajarilgan", value: summary.completed_count },
        { label: "Bekor qilingan", value: summary.cancelled_count },
      ]
    : [];

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold text-slate-900">Xush kelibsiz, {name}</h1>
      <p className="mb-6 text-sm text-slate-500">RTM murojaatlar tizimi bosh sahifasi</p>

      <OverdueAlert requests={myWork} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-2xl font-bold text-brand-700">{c.value}</div>
            <div className="text-xs text-slate-500">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-8 flex gap-3">
        <Link to="/requests" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
          Murojaatlarni ko'rish
        </Link>
        {session.kind === "employee" && (
          <Link to="/requests/new" className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Yangi murojaat
          </Link>
        )}
      </div>
    </div>
  );
}
