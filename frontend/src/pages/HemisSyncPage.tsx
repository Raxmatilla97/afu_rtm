import { useEffect, useState } from "react";
import { hemisSyncApi } from "@/api/reference";
import type { HemisSyncRun } from "@/types";

const STATUS_LABEL: Record<string, string> = {
  running: "Bajarilmoqda...",
  success: "Muvaffaqiyatli",
  failed: "Xatolik",
};

export function HemisSyncPage() {
  const [history, setHistory] = useState<HemisSyncRun[]>([]);
  const [running, setRunning] = useState(false);

  async function load() {
    setHistory(await hemisSyncApi.history());
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const last = history[0];
    if (last?.status !== "running") return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [history]);

  async function handleRun() {
    setRunning(true);
    try {
      await hemisSyncApi.run();
      await load();
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">HEMIS sinxronizatsiya</h1>
        <button
          onClick={handleRun}
          disabled={running || history[0]?.status === "running"}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running || history[0]?.status === "running" ? "Bajarilmoqda..." : "Yangilash"}
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Boshlandi</th>
              <th className="px-4 py-3">Holat</th>
              <th className="px-4 py-3">Bo'limlar (yangi/yangilangan)</th>
              <th className="px-4 py-3">Xodimlar (yangi/yangilangan/bloklangan)</th>
              <th className="px-4 py-3">Xato</th>
            </tr>
          </thead>
          <tbody>
            {history.map((r) => (
              <tr key={r.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3">{new Date(r.started_at).toLocaleString("uz-UZ")}</td>
                <td className="px-4 py-3">{STATUS_LABEL[r.status] || r.status}</td>
                <td className="px-4 py-3 text-slate-500">
                  {r.departments_created} / {r.departments_updated}
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {r.employees_created} / {r.employees_updated} / {r.employees_revoked}
                </td>
                <td className="px-4 py-3 text-red-600">{r.error_message || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
