import { useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { employeesApi } from "@/api/reference";
import type { Employee } from "@/types";

type RoleKey = "is_rtm_staff" | "is_supervisor" | "is_admin" | "is_blocked";

export function EmployeesPage() {
  const [items, setItems] = useState<Employee[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  async function toggle(employee: Employee, key: RoleKey) {
    if (
      key === "is_blocked" &&
      !employee.is_blocked &&
      !window.confirm(
        `${employee.full_name} bloklansinmi?\n\n` +
          "Bu xodim botdan ham, veb-saytdan ham foydalana olmaydi.",
      )
    ) {
      return;
    }

    setBusyId(employee.id);
    setError(null);
    try {
      const updated = await employeesApi.setRoles(employee.id, {
        [key]: !employee[key],
      });
      setItems((prev) => prev.map((x) => (x.id === employee.id ? updated : x)));
    } catch (e) {
      // Never swallow this. A failed toggle used to do nothing at all — no change, no
      // message — which is indistinguishable from a button that was never wired up, and
      // sent us looking in the wrong place entirely.
      setError(describeError(e));
    } finally {
      setBusyId(null);
    }
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

      <p className="mb-4 text-sm text-slate-500">
        <b>RTM xodimi</b> — murojaatlarni bajaradi. <b>Boshliq</b> va <b>Admin</b> — RTM
        guruhida murojaatni boshqa xodimga tayinlay oladi va veb-saytda bajaruvchini olib
        tashlay oladi. <b>Bloklangan</b> xodim tizimga umuman kira olmaydi.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">F.I.Sh.</th>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Bo'lim</th>
                <th className="px-4 py-3">Telegram</th>
                <th className="px-4 py-3">Holat</th>
                <th className="px-4 py-3">Amallar</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr
                  key={e.id}
                  className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                    e.is_blocked ? "bg-red-50/60" : ""
                  }`}
                >
                  <td className="px-4 py-3 font-medium">{e.full_name}</td>
                  <td className="px-4 py-3 text-slate-500">{e.employee_id_number}</td>
                  <td className="px-4 py-3 text-slate-500">{e.department_name || "-"}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {e.telegram_username ? `@${e.telegram_username}` : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {e.is_blocked ? (
                      <span className="text-xs font-medium text-red-600">🚫 Bloklangan</span>
                    ) : e.access_revoked ? (
                      // HEMIS's own verdict, not an administrator's — worth naming
                      // separately so nobody goes looking for who blocked them.
                      <span className="text-xs font-medium text-amber-600">HEMIS: faol emas</span>
                    ) : (
                      <span className="text-xs font-medium text-emerald-600">Faol</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Toggle
                        label="RTM xodimi"
                        on={e.is_rtm_staff}
                        busy={busyId === e.id}
                        onClick={() => toggle(e, "is_rtm_staff")}
                      />
                      <Toggle
                        label="Boshliq"
                        on={e.is_supervisor}
                        tone="violet"
                        busy={busyId === e.id}
                        onClick={() => toggle(e, "is_supervisor")}
                      />
                      <Toggle
                        label="Admin"
                        on={e.is_admin}
                        tone="slate"
                        busy={busyId === e.id}
                        onClick={() => toggle(e, "is_admin")}
                      />
                      <Toggle
                        label={e.is_blocked ? "Blokdan chiqarish" : "Bloklash"}
                        on={e.is_blocked}
                        tone="red"
                        busy={busyId === e.id}
                        onClick={() => toggle(e, "is_blocked")}
                      />
                    </div>
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

function Toggle({
  label,
  on,
  onClick,
  busy,
  tone = "brand",
}: {
  label: string;
  on: boolean;
  onClick: () => void;
  busy: boolean;
  tone?: "brand" | "violet" | "slate" | "red";
}) {
  const active = {
    brand: "bg-brand-600 text-white border-brand-600",
    violet: "bg-violet-600 text-white border-violet-600",
    slate: "bg-slate-700 text-white border-slate-700",
    red: "bg-red-600 text-white border-red-600",
  }[tone];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
        on ? active : "border-slate-300 text-slate-600 hover:bg-slate-100"
      }`}
    >
      {on ? "✓ " : ""}
      {label}
    </button>
  );
}
