import { useEffect, useState } from "react";
import { employeesApi } from "@/api/reference";
import type { Employee } from "@/types";

export function EmployeesPage() {
  const [items, setItems] = useState<Employee[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setItems(await employeesApi.list({ q: q || undefined }));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [q]);

  async function toggleStaff(e: Employee) {
    const updated = e.is_rtm_staff ? await employeesApi.demote(e.id) : await employeesApi.promote(e.id);
    setItems((prev) => prev.map((x) => (x.id === e.id ? updated : x)));
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Xodimlar</h1>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ism yoki ID bo'yicha qidirish..."
          className="w-72 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">F.I.Sh.</th>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Bo'lim</th>
                <th className="px-4 py-3">Telegram</th>
                <th className="px-4 py-3">Holat</th>
                <th className="px-4 py-3">RTM xodimi</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium">{e.full_name}</td>
                  <td className="px-4 py-3 text-slate-500">{e.employee_id_number}</td>
                  <td className="px-4 py-3 text-slate-500">{e.department_name || "-"}</td>
                  <td className="px-4 py-3 text-slate-500">{e.telegram_username ? `@${e.telegram_username}` : "-"}</td>
                  <td className="px-4 py-3">
                    {e.access_revoked ? (
                      <span className="text-xs font-medium text-red-600">Bloklangan</span>
                    ) : (
                      <span className="text-xs font-medium text-emerald-600">Faol</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleStaff(e)}
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        e.is_rtm_staff ? "bg-brand-600 text-white" : "border border-slate-300 text-slate-600"
                      }`}
                    >
                      {e.is_rtm_staff ? "Ha" : "Yo'q"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
