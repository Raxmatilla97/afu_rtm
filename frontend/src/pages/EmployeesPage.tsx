import { useEffect, useRef, useState, type ReactNode } from "react";
import { describeError } from "@/api/errors";
import { departmentsApi, employeesApi } from "@/api/reference";
import { EmployeeAvatar } from "@/components/EmployeeAvatar";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import type { Department, Employee } from "@/types";

type RoleKey = "is_rtm_staff" | "is_supervisor" | "is_admin" | "is_blocked";

/** What the edit form can write. Everything else on the record is read-only by design. */
interface Draft {
  full_name: string;
  department_id: string;
  phone_number: string;
  telegram_username: string;
  recovery_email: string;
  hemis_email: string;
  hemis_phone: string;
  year_of_enter: string;
}

function draftFrom(employee: Employee): Draft {
  return {
    full_name: employee.full_name,
    department_id: employee.department_id ? String(employee.department_id) : "",
    phone_number: employee.phone_number ?? "",
    telegram_username: employee.telegram_username ?? "",
    recovery_email: employee.recovery_email ?? "",
    hemis_email: employee.hemis_email ?? "",
    hemis_phone: employee.hemis_phone ?? "",
    year_of_enter: employee.year_of_enter ? String(employee.year_of_enter) : "",
  };
}

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

  /**
   * Put a freshly saved employee back into the table and the open dialog.
   *
   * `request_count` is carried over from the row we already had. Only the list endpoint
   * counts requests; every single-employee endpoint answers with zero, so writing the
   * response straight into the table would blank the "Murojaatlar" column the moment
   * anybody toggled a role or saved a phone number.
   */
  function applyUpdate(updated: Employee) {
    const withCount = (previous: Employee): Employee => ({
      ...updated,
      request_count: updated.request_count || previous.request_count,
    });
    setItems((prev) => prev.map((x) => (x.id === updated.id ? withCount(x) : x)));
    // The dialog holds its own copy of the row, so a change made inside it would otherwise
    // keep showing the old state until it was closed and reopened.
    setDetail((current) => (current && current.id === updated.id ? withCount(current) : current));
  }

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
      applyUpdate(await employeesApi.setRoles(employee.id, { [key]: !employee[key] }));
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
        Ism yoki «👁 Batafsil» tugmasi bosilsa, xodimning to'liq ma'lumoti ochiladi — u yerdan
        «✏️ Tahrirlash» orqali ma'lumotni va suratni o'zgartirish mumkin.
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
          departments={departments}
          busy={busyId === detail.id}
          onToggle={(key) => toggle(detail, key)}
          onUpdated={applyUpdate}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

/**
 * Everything the panel knows about one person, in one dialog — and now the only place it
 * can be corrected.
 *
 * The table can carry four columns before it stops being readable, and the questions that
 * actually get asked about an employee — is their Telegram linked, did they ever log in
 * through HEMIS, when were they last synced, why is there no photo — all live in the
 * columns that had to be left out. So the row stays short and the whole record lives here.
 *
 * The dialog has two modes. Reading is the default because that is what it is opened for
 * ninety times out of a hundred, and a screen full of input boxes is much harder to scan
 * than a screen full of facts. «Tahrirlash» turns the same layout into a form in place, so
 * nothing moves and the value being changed stays where the eye already was.
 *
 * The role toggles are repeated inside on purpose: whoever opened this is deciding
 * something, and closing the dialog to press a button in the row behind it is exactly the
 * detour that ends with the wrong person being blocked.
 */
function EmployeeDetailModal({
  employee,
  departments,
  busy,
  onToggle,
  onUpdated,
  onClose,
}: {
  employee: Employee;
  departments: Department[];
  busy: boolean;
  onToggle: (key: RoleKey) => void;
  onUpdated: (employee: Employee) => void;
  onClose: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(employee));
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Escape closes the dialog while reading. In edit mode it drops the changes instead,
    // which is one keypress away from losing work — so it asks first.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (!editing) onClose();
      else if (window.confirm("Saqlanmagan o'zgarishlar bekor qilinsinmi?")) setEditing(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, editing]);

  // Three different situations look identical in the list — a circle with initials. This
  // is the only place that tells them apart, and two of the three are fixable.
  const photoNote = employee.image_manual_at
    ? "Surat qo'lda yuklangan — HEMIS sinxronizatsiyasi uni o'zgartirmaydi."
    : employee.image_local_path
      ? "Surat HEMIS'dan yuklab olingan."
      : employee.image_source_url
        ? "HEMIS surat manzilini bergan, ammo fayl yuklab olinmagan. HEMIS sinxronizatsiyasini qayta ishga tushiring — yetishmayotgan suratlar qaytadan yuklanadi."
        : "HEMIS'da bu xodimning surati yo'q. «Tahrirlash» tugmasini bosib, surat ustiga bosing va o'zingiz yuklang.";

  function startEditing() {
    setDraft(draftFrom(employee));
    setFormError(null);
    setEditing(true);
  }

  function cancelEditing() {
    setDraft(draftFrom(employee));
    setFormError(null);
    setEditing(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    // A submit while nothing is being edited is always spurious — the dialog is a <form>
    // for the whole of its life, so anything that reaches the browser's default submit
    // behaviour lands here. Saving in that state writes the record back over itself and
    // silently leaves edit mode, which looks exactly like the dialog refusing to open.
    if (!editing || saving) return;
    if (!draft.full_name.trim()) {
      setFormError("F.I.Sh. bo'sh bo'lishi mumkin emas.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      // Sent whole rather than diffed: every one of these fields accepts null as a real
      // value ("clear it"), so a diff would have to distinguish "unchanged" from "emptied"
      // and the server already only writes what it is given.
      onUpdated(
        await employeesApi.update(employee.id, {
          full_name: draft.full_name.trim(),
          department_id: draft.department_id ? Number(draft.department_id) : null,
          phone_number: draft.phone_number.trim() || null,
          telegram_username: draft.telegram_username.trim() || null,
          recovery_email: draft.recovery_email.trim() || null,
          hemis_email: draft.hemis_email.trim() || null,
          hemis_phone: draft.hemis_phone.trim() || null,
          year_of_enter: draft.year_of_enter ? Number(draft.year_of_enter) : null,
        }),
      );
      setEditing(false);
    } catch (err) {
      setFormError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handlePhoto(file: File) {
    setSaving(true);
    setFormError(null);
    try {
      onUpdated(await employeesApi.uploadPhoto(employee.id, file));
    } catch (err) {
      setFormError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleRemovePhoto() {
    if (!window.confirm("Surat o'chirilsinmi? HEMIS'da surat bo'lsa, keyingi sinxronizatsiyada qayta yuklanadi.")) {
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      onUpdated(await employeesApi.deletePhoto(employee.id));
    } catch (err) {
      setFormError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const set = (key: keyof Draft) => (value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-2 sm:items-center sm:p-4">
      {/* Wider and taller than it was. The record has four sections and a role strip, and
          at max-w-3xl every one of them wrapped into two lines on a laptop. */}
      <form
        onSubmit={handleSave}
        className="flex max-h-[95vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
          <div className="flex min-w-0 items-start gap-4">
            <div className="shrink-0">
              <button
                type="button"
                onClick={() => editing && photoInput.current?.click()}
                disabled={!editing || saving}
                aria-label={editing ? "Yangi surat yuklash" : employee.full_name}
                title={editing ? "Yangi surat yuklash uchun bosing" : undefined}
                className={`group relative block rounded-full ${
                  editing ? "cursor-pointer" : "cursor-default"
                }`}
              >
                <EmployeeAvatar
                  name={employee.full_name}
                  imagePath={employee.image_local_path}
                  size="xl"
                />
                {editing && (
                  // Always visible rather than on hover: on a touch screen there is no
                  // hover, and "the photo is a button" is not guessable otherwise.
                  <span className="absolute inset-0 flex items-center justify-center rounded-full bg-slate-900/45 text-2xl text-white opacity-90 transition-opacity group-hover:opacity-100">
                    📷
                  </span>
                )}
              </button>
              <input
                ref={photoInput}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) handlePhoto(file);
                }}
              />
              {editing && employee.image_local_path && (
                <button
                  type="button"
                  onClick={handleRemovePhoto}
                  disabled={saving}
                  className="mt-2 w-28 rounded-lg border border-slate-300 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  Suratni o'chirish
                </button>
              )}
            </div>

            <div className="min-w-0">
              {editing ? (
                <input
                  value={draft.full_name}
                  onChange={(e) => set("full_name")(e.target.value)}
                  className="w-full min-w-0 rounded-lg border border-slate-300 px-3 py-1.5 text-lg font-bold text-slate-900 sm:w-96"
                />
              ) : (
                <h2 className="truncate text-lg font-bold text-slate-900 sm:text-xl">
                  {employee.full_name}
                </h2>
              )}
              <p className="mt-0.5 truncate text-sm text-slate-500">
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

          {/* At the top, where the decision to edit is made — not at the bottom of a
              dialog that has to be scrolled to reach it.

              The keys are load-bearing, not tidiness. Without them React sees a <button>
              in the same slot before and after the switch, keeps the DOM node and merely
              patches its attributes — so «Tahrirlash» turns into type="submit" *during*
              the click that pressed it, and the browser then runs its default action on
              what is now a submit button. The form submitted, saved nothing, and dropped
              straight back out of edit mode a few milliseconds later. Distinct keys make
              React build new nodes instead of mutating the one being clicked. */}
          <div className="flex shrink-0 items-center gap-2">
            {editing ? (
              <>
                <button
                  key="save"
                  type="submit"
                  disabled={saving}
                  className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  {saving ? "Saqlanmoqda..." : "💾 Saqlash"}
                </button>
                <button
                  key="cancel"
                  type="button"
                  onClick={cancelEditing}
                  disabled={saving}
                  className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  Bekor qilish
                </button>
              </>
            ) : (
              <>
                <button
                  key="edit"
                  type="button"
                  onClick={startEditing}
                  className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700"
                >
                  ✏️ Tahrirlash
                </button>
                <button
                  key="close"
                  type="button"
                  onClick={onClose}
                  aria-label="Yopish"
                  className="min-h-11 px-2 text-slate-400 hover:text-slate-700"
                >
                  ✖
                </button>
              </>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {formError && <ErrorBanner message={formError} />}

          {editing && (
            <p className="mb-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
              ⚠️ <b>F.I.Sh.</b>, <b>bo'lim</b> va <b>ishga kirgan yil</b> HEMIS'dan keladi —
              keyingi sinxronizatsiyada bu maydonlar HEMIS'dagi qiymatga qaytadi. Telefon,
              Telegram, tiklash pochtasi va qo'lda yuklangan surat esa faqat shu yerda
              boshqariladi va sinxronizatsiya ularga tegmaydi.
            </p>
          )}

          <div className="grid gap-x-8 lg:grid-cols-2">
            <div>
              <Section title="Aloqa">
                {editing ? (
                  <>
                    <EditRow
                      label="Telefon"
                      value={draft.phone_number}
                      onChange={set("phone_number")}
                      placeholder="+998 90 123 45 67"
                    />
                    <EditRow
                      label="Telegram"
                      value={draft.telegram_username}
                      onChange={set("telegram_username")}
                      placeholder="foydalanuvchi (@ siz)"
                    />
                  </>
                ) : (
                  <>
                    <Row label="Telefon" value={employee.phone_number} />
                    <Row
                      label="Telegram"
                      value={employee.telegram_username ? `@${employee.telegram_username}` : null}
                    />
                  </>
                )}
                <Row label="Telegram ID" value={employee.telegram_user_id?.toString() ?? null} />
                <Row label="Telegram tasdiqlangan" value={fmtDateTime(employee.verified_at)} />
              </Section>

              <Section title="Bo'lim va lavozim">
                {editing ? (
                  <>
                    <SelectRow
                      label="Bo'lim"
                      value={draft.department_id}
                      onChange={set("department_id")}
                      options={departments.map((d): [string, string] => [String(d.id), d.name])}
                      emptyLabel="— bo'lim biriktirilmagan —"
                    />
                    <EditRow
                      label="Ishga kirgan yili"
                      value={draft.year_of_enter}
                      onChange={set("year_of_enter")}
                      type="number"
                      placeholder="2019"
                    />
                  </>
                ) : (
                  <>
                    <Row label="Bo'lim" value={employee.department_name} />
                    <Row
                      label="Ishga kirgan yili"
                      value={employee.year_of_enter?.toString() ?? null}
                    />
                  </>
                )}
                <Row label="Xodim ID raqami" value={employee.employee_id_number} />
                <Row label="Holat kodi" value={employee.employee_status_code} />
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
                {editing ? (
                  <EditRow
                    label="Tiklash pochtasi"
                    value={draft.recovery_email}
                    onChange={set("recovery_email")}
                    type="email"
                    placeholder="ism@afu.uz"
                  />
                ) : (
                  <Row label="Tiklash pochtasi" value={employee.recovery_email} />
                )}
              </Section>
            </div>

            <div>
              <Section title="HEMIS ma'lumotlari">
                <Row label="HEMIS ID" value={employee.hemis_id?.toString() ?? null} />
                <Row label="Login" value={employee.hemis_login} />
                {editing ? (
                  <>
                    <EditRow
                      label="Email"
                      value={draft.hemis_email}
                      onChange={set("hemis_email")}
                      type="email"
                    />
                    <EditRow
                      label="Telefon (HEMIS)"
                      value={draft.hemis_phone}
                      onChange={set("hemis_phone")}
                    />
                  </>
                ) : (
                  <>
                    <Row label="Email" value={employee.hemis_email} />
                    <Row label="Telefon (HEMIS)" value={employee.hemis_phone} />
                  </>
                )}
                <Row label="Universitet ID" value={employee.hemis_university_id} />
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
                    employee.is_blocked ? `Ha · ${fmtDateTime(employee.blocked_at) ?? "—"}` : "Yo'q"
                  }
                />
                <Row label="Surat fayli" value={employee.image_local_path} />
                <Row label="Surat qo'lda yuklangan" value={fmtDateTime(employee.image_manual_at)} />
              </Section>
            </div>
          </div>

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
              busy={busy || saving}
              onClick={() => onToggle("is_rtm_staff")}
            />
            <Toggle
              label="Boshliq"
              on={employee.is_supervisor}
              tone="violet"
              busy={busy || saving}
              onClick={() => onToggle("is_supervisor")}
            />
            <Toggle
              label="Admin"
              on={employee.is_admin}
              tone="slate"
              busy={busy || saving}
              onClick={() => onToggle("is_admin")}
            />
            <Toggle
              label={employee.is_blocked ? "Blokdan chiqarish" : "Bloklash"}
              on={employee.is_blocked}
              tone="red"
              busy={busy || saving}
              onClick={() => onToggle("is_blocked")}
            />
          </div>
        </div>

        {/* Keyed for the same reason as the header buttons above: a <button> that keeps
            its DOM node across the switch has its `type` rewritten mid-click. */}
        <footer className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          {editing ? (
            <>
              <button
                key="cancel"
                type="button"
                onClick={cancelEditing}
                disabled={saving}
                className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                Bekor qilish
              </button>
              <button
                key="save"
                type="submit"
                disabled={saving}
                className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {saving ? "Saqlanmoqda..." : "💾 Saqlash"}
              </button>
            </>
          ) : (
            <button
              key="close"
              type="button"
              onClick={onClose}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50"
            >
              Yopish
            </button>
          )}
        </footer>
      </form>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </h3>
      <dl>{children}</dl>
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

/**
 * The editable twin of `Row`.
 *
 * Same label on the same side at the same height, so switching into edit mode does not
 * reflow the dialog — the value the reader was looking at stays exactly where it was and
 * simply becomes typable.
 */
function EditRow({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 py-1.5">
      <dt className="shrink-0 text-xs text-slate-400">{label}</dt>
      <dd className="min-w-0 flex-1">
        <input
          type={type}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-2 py-1 text-right text-sm text-slate-800 focus:border-brand-500 focus:outline-none"
        />
      </dd>
    </div>
  );
}

function SelectRow({
  label,
  value,
  onChange,
  options,
  emptyLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  emptyLabel: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 py-1.5">
      <dt className="shrink-0 text-xs text-slate-400">{label}</dt>
      <dd className="min-w-0 flex-1">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-2 py-1 text-sm text-slate-800 focus:border-brand-500 focus:outline-none"
        >
          <option value="">{emptyLabel}</option>
          {options.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </dd>
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
