import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { requestsApi } from "@/api/requests";
import { StatusBadge } from "@/components/StatusBadge";
import type { RequestItem } from "@/types";

export function RequestsListPage() {
  const [items, setItems] = useState<RequestItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    requestsApi
      .list(statusFilter || undefined)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Murojaatlar</h1>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        >
          <option value="">Barcha holatlar</option>
          <option value="new">Yangi</option>
          <option value="assigned">Tayinlangan</option>
          <option value="in_progress">Jarayonda</option>
          <option value="completed">Bajarilgan</option>
          <option value="cancelled">Bekor qilingan</option>
        </select>
      </div>

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-400">
          Murojaatlar topilmadi
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">№</th>
                <th className="px-4 py-3">Kategoriya</th>
                <th className="px-4 py-3">Murojaatchi</th>
                <th className="px-4 py-3">Tayinlangan</th>
                <th className="px-4 py-3">Holat</th>
                <th className="px-4 py-3">Yaratilgan</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/requests/${r.id}`} className="font-medium text-brand-700 hover:underline">
                      {r.display_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{r.category_label}</td>
                  <td className="px-4 py-3">{r.requester_name}</td>
                  <td className="px-4 py-3">{r.assigned_to_name || "-"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">{new Date(r.created_at).toLocaleString("uz-UZ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
