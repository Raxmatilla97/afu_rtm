import { useEffect, useState } from "react";
import { departmentsApi } from "@/api/reference";
import type { Department } from "@/types";

export function DepartmentsPage() {
  const [items, setItems] = useState<Department[]>([]);

  useEffect(() => {
    departmentsApi.list().then(setItems);
  }, []);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Bo'limlar</h1>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Nomi</th>
              <th className="px-4 py-3">Kod</th>
              <th className="px-4 py-3">HEMIS ID</th>
              <th className="px-4 py-3">Holat</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium">{d.name}</td>
                <td className="px-4 py-3 text-slate-500">{d.code || "-"}</td>
                <td className="px-4 py-3 text-slate-500">{d.hemis_id}</td>
                <td className="px-4 py-3">
                  {d.is_active ? (
                    <span className="text-xs font-medium text-emerald-600">Faol</span>
                  ) : (
                    <span className="text-xs font-medium text-red-600">Nofaol</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
