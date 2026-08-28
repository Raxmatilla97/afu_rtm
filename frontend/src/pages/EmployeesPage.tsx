import { useEffect, useState, type ReactNode } from "react";
import { describeError } from "@/api/errors";
import { departmentsApi, employeesApi } from "@/api/reference";
import { EmployeeAvatar } from "@/components/EmployeeAvatar";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import type { Department, Employee } from "@/types";

type RoleKey = "is_rtm_staff" | "is_supervisor" | "is_admin" | "is_blocked";

export function EmployeesPage() {
  const [items, setItems] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [q, setQ] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [staffOnly, setStaffOnly] = useState(false);
  const [sort, setSort] = useState<"name" | "requests">("name");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Employee | null>(null);

  async function load() {
    setLoading(true);
    try {
      // Filtering and sorting happen on the server: the list is capped at 500 rows, so
      // narrowing it here would sort and filter only the first 500 names alphabetically —
      // and "who files the most requests" would then be wrong by construction.
      setItems(
        await employeesApi.list({
          q: q || undefined,
          departmentId: departmentId ? Number(departmentId) : undefined,
          isRtmStaff: staffOnly ? true : undefined,
          sort,
        }),
      );
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // Debounced because `q` changes on every keystroke; the other three are single clicks
    // and simply ride along.
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [q, departmentId, staffOnly, sort]);

  useEffect(() => {
    departmentsApi.list().then(setDepartments).catch(() => setDepartments([]));
  }, []);

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
      // The dialog holds its own copy of the row, so a toggle pressed inside it would
      // otherwise keep showing the old state until it was closed and reopened.
      setDetail((current) => (current && current.id === employee.id ? updated : current));
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
        <button
          type="button"
          onClick={() => setDetail(e)}
          className="flex w-full items-center gap-3 text-left"
        >
          {/* md rather than sm: the photo is here to be recognised across a desk, not to
              decorate the row. */}
          <EmployeeAvatar name={e.full_name} imagePath={e.image_local_path} size="md" />
          <div className="min-w-0">
            <div className="truncate font-medium text-slate-900 hover:text-brand-700">
              {e.full_name}
            </div>
            <div className="truncate text-xs font-normal text-slate-400">
              {e.employee_id_number}
              {e.department_name ? ` · ${e.department_name}` : ""}
            </div>
          </div>
        </button>
      ),
    },
    {
      key: "requests",
      header: "Murojaatlar",
      align: "right",
      cell: (e) => (
        <span
          className={`tabular-nums ${
            e.request_count > 0 ? "font-medium text-slate-800" : "text-slate-400"
          }`}
        >
          {e.request_count}
        </span>
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
          <button
            type="button"
            onClick={() => setDetail(e)}
            className="min-h-9 rounded-full border border-slate-300 px-3 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            👁 Batafsil
          </button>
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
    // Full width: four role toggles plus a photo need every pixel the screen has.
    <div>
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
        Ism yoki «👁 Batafsil» tugmasi bosilsa, xodimning to'liq ma'lumoti ochiladi.
      </p>

      {error && <ErrorBanner message={error} />}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={departmentId}
          onChange={(e) => setDepartmentId(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto sm:max-w-xs"
        >
          <option value="">Barcha bo'limlar</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "name" | "requests")}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="name">F.I.Sh. bo'yicha (A-Z)</option>
          <option value="requests">Ko'p murojaat yuborganlar</option>
        </select>

        <label className="flex min-h-11 items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={staffOnly}
            onChange={(e) => setStaffOnly(e.target.checked)}
          />
          Faqat RTM xodimlari
        </label>

        {(departmentId || staffOnly || sort !== "name" || q) && (
          <button
            onClick={() => {
              setDepartmentId("");
              setStaffOnly(false);
              setSort("name");
              setQ("");
            }}
            className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-100"
          >
            ✖ Filtrni tozalash
          </button>
        )}

        <span className="text-sm text-slate-400">{items.length} ta xodim</span>
      </div>

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

      {detail && (
        <EmployeeDetailModal
          employee={detail}
          busy={busyId === detail.id}
          onToggle={(key) => toggle(detail, key)}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

/**
 * Everything the panel knows about one person, in one dialog.
 *
 * The table can carry four columns before it stops being readable, and the questions that
 * actually get asked about an employee — is their Telegram linked, did they ever log in
 * through HEMIS, when were they last synced, why is there no photo — all live in the
 * columns that had to be left out. So the row stays short and the whole record lives here.
 *
 * The role toggles are repeated inside on purpose: whoever opened this is deciding
 * something, and closing the dialog to press a button in the row behind it is exactly the
 * detour that ends with the wrong person being blocked.
 */
function EmployeeDetailModal({
  employee,
  busy,
  onToggle,
  onClose,
}: {
  employee: Employee;
  busy: boolean;
  onToggle: (key: RoleKey) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Three different situations look identical in the list — a circle with initials. This
  // is the only place that tells them apart, and the middle one is fixable.
  const photoNote = employee.image_local_path
    ? "Surat HEMIS'dan yuklab olingan."
    : employee.image_source_url
      ? "HEMIS surat manzilini bergan, ammo fayl yuklab olinmagan. HEMIS sinxronizatsiyasini qayta ishga tushiring — yetishmayotgan suratlar qaytadan yuklanadi."
      : "HEMIS'da bu xodimning surati yo'q.";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
          <div className="flex min-w-0 items-center gap-4">
            <EmployeeAvatar
              name={employee.full_name}
              imagePath={employee.image_local_path}
              size="xl"
            />
            <div className="min-w-0">
              <h2 className="truncate text-lg font-bold text-slate-900 sm:text-xl">
                {employee.full_name}
              </h2>
              <p className="truncate text-sm text-slate-500">
                {employee.employee_id_number}
                {employee.department_name ? ` · ${employee.department_name}` : ""}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {employee.is_blocked && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                    🚫 Bloklangan
                  </span>
                )}
                {employee.access_revoked && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                    HEMIS: faol emas
                  </span>
                )}
                {!employee.is_blocked && !employee.access_revoked && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                    Faol
                  </span>
                )}
                {employee.is_admin && (
                  <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-white">
                    Admin
                  </span>
                )}
                {employee.is_supervisor && (
                  <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">
                    Boshliq
                  </span>
                )}
                {employee.is_rtm_staff && (
                  <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                    RTM xodimi
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Yopish"
            className="shrink-0 text-slate-400 hover:text-slate-700"
          >
            ✖
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          <Section title="Aloqa">
            <Row label="Telefon" value={employee.phone_number} />
            <Row
              label="Telegram"
              value={employee.telegram_username ? `@${employee.telegram_username}` : null}
            />
            <Row label="Telegram ID" value={employee.telegram_user_id?.toString() ?? null} />
            <Row label="Telegram tasdiqlangan" value={fmtDateTime(employee.verified_at)} />
          </Section>

          <Section title="HEMIS ma'lumotlari">
            <Row label="HEMIS ID" value={employee.hemis_id?.toString() ?? null} />
            <Row label="Login" value={employee.hemis_login} />
            <Row label="Email" value={employee.hemis_email} />
            <Row label="Telefon (HEMIS)" value={employee.hemis_phone} />
            <Row label="Universitet ID" value={employee.hemis_university_id} />
            <Row label="Holat kodi" value={employee.employee_status_code} />
            <Row label="Ishga kirgan yili" value={employee.year_of_enter?.toString() ?? null} />
            <Row label="HEMIS orqali kirgan" value={fmtDateTime(employee.oauth_verified_at)} />
            <Row label="Oxirgi sinxronizatsiya" value={fmtDateTime(employee.last_synced_at)} />
          </Section>

          <Section title="Tizimdagi holati">
            <Row label="Ro'yxatga olingan" value={fmtDateTime(employee.created_at)} />
            <Row
              label="HEMIS kirish huquqi"
              value={
                employee.access_revoked
                  ? `Bekor qilingan · ${fmtDateTime(employee.access_revoked_at) ?? "—"}`
                  : "Faol"
              }
            />
            <Row
              label="Blok"
              value={
                employee.is_blocked
                  ? `Ha · ${fmtDateTime(employee.blocked_at) ?? "—"}`
                  : "Yo'q"
              }
            />
            <Row label="Surat fayli" value={employee.image_local_path} />
          </Section>

          <Section title="Tezkor kirish">
            <Row
              label="Parol o'rnatilgan"
              value={
                employee.has_quick_password
                  ? fmtDateTime(employee.password_set_at) ?? "ha"
                  : "yo'q — hisob hali egallanmagan"
              }
            />
            <Row label="Tiklash pochtasi" value={employee.recovery_email} />
          </Section>

          <p className="mb-6 rounded-lg bg-slate-50 px-4 py-3 text-xs text-slate-600">
            🖼 {photoNote}
          </p>

          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Rollar
          </h3>
          <div className="flex flex-wrap gap-1.5">
            <Toggle
              label="RTM xodimi"
              on={employee.is_rtm_staff}
              busy={busy}
              onClick={() => onToggle("is_rtm_staff")}
            />
            <Toggle
              label="Boshliq"
              on={employee.is_supervisor}
              tone="violet"
              busy={busy}
              onClick={() => onToggle("is_supervisor")}
            />
            <Toggle
              label="Admin"
              on={employee.is_admin}
              tone="slate"
              busy={busy}
              onClick={() => onToggle("is_admin")}
            />
            <Toggle
              label={employee.is_blocked ? "Blokdan chiqarish" : "Bloklash"}
              on={employee.is_blocked}
              tone="red"
              busy={busy}
              onClick={() => onToggle("is_blocked")}
            />
          </div>
        </div>

        <footer className="border-t border-slate-200 px-5 py-3 text-right">
          <button
            onClick={onClose}
            className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50"
          >
            Yopish
          </button>
        </footer>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </h3>
      <dl className="grid gap-x-8 sm:grid-cols-2">{children}</dl>
    </section>
  );
}

/** One labelled fact. Empty and unknown both read as "—" rather than as a blank line. */
function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5">
      <dt className="shrink-0 text-xs text-slate-400">{label}</dt>
      <dd className="min-w-0 break-all text-right text-sm text-slate-800">{value || "—"}</dd>
    </div>
  );
}

function fmtDateTime(value: string | null | undefined): string | null {
  return value ? new Date(value).toLocaleString("uz-UZ") : null;
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
