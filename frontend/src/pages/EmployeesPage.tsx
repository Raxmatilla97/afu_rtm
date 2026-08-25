import { useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { employeesApi } from "@/api/reference";
import { EmployeeAvatar } from "@/components/EmployeeAvatar";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
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
      setError(null);
    } catch (e) {
      setError(describeError(e));
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
      const updated = await employeesApi.setRoles(employee.id, { [key]: !employee[key] });
      setItems((prev) => prev.map((x) => (x.id === employee.id ? updated : x)));
    } catch (e) {
      // Never swallow this. A failed toggle that does nothing at all is indistinguishable
      // from a button that was never wired up.
      setError(describeError(e));
    } finally {
      setBusyId(null);
    }
  }

  const columns: Column<Employee>[] = [
    {
      key: "name",
      header: "F.I.Sh.",
      mobile: "title",
      cell: (e) => (
        <div className="flex items-center gap-3">
          <EmployeeAvatar name={e.full_name} imagePath={e.image_local_path} size="sm" />
          <div className="min-w-0">
            <div className="truncate font-medium">{e.full_name}</div>
            <div className="truncate text-xs font-normal text-slate-400">
              {e.employee_id_number}
              {e.department_name ? ` · ${e.department_name}` : ""}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "telegram",
      header: "Telegram",
      cell: (e) => (
        <span className="text-slate-500">
          {e.telegram_username ? `@${e.telegram_username}` : "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Holat",
      cell: (e) =>
        e.is_blocked ? (
          <span className="text-xs font-medium text-red-600">🚫 Bloklangan</span>
        ) : e.access_revoked ? (
          // HEMIS's own verdict, not an administrator's — named separately so nobody goes
          // looking for who blocked them.
          <span className="text-xs font-medium text-amber-600">HEMIS: faol emas</span>
        ) : (
          <span className="text-xs font-medium text-emerald-600">Faol</span>
        ),
    },
    {
      key: "roles",
      header: "Amallar",
      cell: (e) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
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
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Xodimlar"
        subtitle="Rollar va kirish huquqlari"
        action={
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ism yoki ID..."
            className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-64"
          />
        }
      />

      <p className="mb-4 text-sm text-slate-500">
        <b>RTM xodimi</b> — murojaatlarni bajaradi. <b>Boshliq</b> va <b>Admin</b> — guruhda
        murojaatni tayinlay oladi va veb-saytda bajaruvchini olib tashlaydi; <b>Admin</b> qo'shimcha
        ravishda to'liq admin panelga kiradi. <b>Bloklangan</b> xodim tizimga umuman kira olmaydi.
      </p>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <ResponsiveTable
          rows={items}
          columns={columns}
          rowKey={(e) => e.id}
          empty="Xodim topilmadi"
          rowClass={(e) => (e.is_blocked ? "bg-red-50/60" : "")}
        />
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
      className={`min-h-9 rounded-full border px-3 text-xs font-medium transition-colors disabled:opacity-50 ${
        on ? active : "border-slate-300 text-slate-600 hover:bg-slate-100"
      }`}
    >
      {on ? "✓ " : ""}
      {label}
    </button>
  );
}
