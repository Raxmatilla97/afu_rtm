import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { describeError } from "@/api/errors";
import { categoriesApi, employeesApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import { STATUS_LABELS, type Category, type Employee, type RequestItem } from "@/types";

// "Barcha holatlar" means every status except returned: the server leaves returned
// requests out of an unfiltered list, because a rejected request is not work waiting to be
// done. Picking the last option here is the only way to see them, which is the point.
const STATUS_FILTERS = [
  ["", "Barcha holatlar (qaytarilganlarsiz)"],
  ["new", STATUS_LABELS.new],
  ["assigned", STATUS_LABELS.assigned],
  ["in_progress", STATUS_LABELS.in_progress],
  ["waiting", STATUS_LABELS.waiting],
  ["completed", STATUS_LABELS.completed],
  ["cancelled", STATUS_LABELS.cancelled],
  ["returned", "🚫 " + STATUS_LABELS.returned],
] as const;

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

export function RequestsListPage() {
  const { isAdmin, session } = useAuth();
  // Boshliq and Admin see the whole queue, so they are the only ones for whom "filter by
  // staff member" means anything — everybody else is already looking at one person's work.
  const canManage =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

  const [items, setItems] = useState<RequestItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [staff, setStaff] = useState<Employee[]>([]);

  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Which rows are ticked for deletion. Admin only, and cleared whenever the list is
  // refetched — a selection that survives a filter change would delete rows nobody can see.
  const [selected, setSelected] = useState<number[]>([]);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    categoriesApi.list().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!canManage) return;
    employeesApi.rtmStaff().then(setStaff).catch(() => setStaff([]));
  }, [canManage]);

  // Filtering happens on the server: the list is capped at 200 rows, so narrowing it here
  // would only ever filter the newest 200 and quietly hide the rest.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(
        await requestsApi.list({
          status: statusFilter || undefined,
          categorySlug: categoryFilter || undefined,
          assigneeEmployeeId: assigneeFilter ? Number(assigneeFilter) : undefined,
        }),
      );
      setSelected([]);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, categoryFilter, assigneeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const filtersActive = Boolean(statusFilter || categoryFilter || assigneeFilter);
  const allSelected = items.length > 0 && selected.length === items.length;

  function toggleRow(id: number) {
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );
  }

  /**
   * Erase the ticked requests. Admin only.
   *
   * This exists because the queue fills up with requests filed while testing, and there is
   * no other way to get rid of them: returning and cancelling both leave the row in the
   * statistics, which is the opposite of what is wanted. The count is spelled out in the
   * confirmation because that is the number that gets misread, not the button.
   */
  async function deleteSelected() {
    if (selected.length === 0) return;
    const numbers = items
      .filter((r) => selected.includes(r.id))
      .map((r) => r.display_number)
      .join(", ");
    if (
      !window.confirm(
        `${selected.length} ta murojaat butunlay o'chiriladi:\n${numbers}\n\n` +
          "Yozishmalar, fayllar va guruhdagi kartochkalar ham o'chadi. " +
          "Buni ortga qaytarib bo'lmaydi.",
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await requestsApi.bulkRemove(selected);
      await load();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setDeleting(false);
    }
  }

  async function deleteOne(request: RequestItem) {
    if (
      !window.confirm(
        `${request.display_number} butunlay o'chiriladi — yozishmalar, fayllar va ` +
          "guruhdagi kartochka bilan birga. Buni ortga qaytarib bo'lmaydi.",
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await requestsApi.remove(request.id);
      await load();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setDeleting(false);
    }
  }

  const columns: Column<RequestItem>[] = [
    {
      key: "number",
      header: "№",
      mobile: "title",
      // The tick box lives inside the number cell rather than in a column of its own: the
      // responsive table turns every extra column into a labelled line on a phone, and
      // "Tanlash: ☐" as its own row is worse than a box next to the number it selects.
      cell: (r) => (
        <div className="flex items-center gap-2.5">
          {isAdmin && (
            <input
              type="checkbox"
              checked={selected.includes(r.id)}
              onChange={() => toggleRow(r.id)}
              aria-label={`${r.display_number} ni tanlash`}
              className="h-4 w-4 shrink-0 accent-red-600"
            />
          )}
          <Link to={`/requests/${r.id}`} className="font-medium text-brand-700 hover:underline">
            {r.display_number}
          </Link>
        </div>
      ),
    },
    { key: "category", header: "Kategoriya", mobile: "meta", cell: (r) => r.category_label },
    { key: "requester", header: "Murojaatchi", cell: (r) => r.requester_name || "—" },
    {
      key: "assignees",
      header: "Bajaruvchi",
      cell: (r) =>
        r.assignees.length === 0
          ? "—"
          : r.assignees.map((a) => a.full_name).join(", "),
    },
    { key: "status", header: "Holat", cell: (r) => <StatusBadge status={r.status} /> },
    {
      key: "created",
      header: "Yaratilgan",
      cell: (r) => <span className="text-slate-500">{shortDate(r.created_at)}</span>,
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (r) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
          <Link
            to={`/requests/${r.id}`}
            className="inline-flex min-h-9 items-center rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
          >
            👁 Ko'rish
          </Link>
          {isAdmin && (
            <button
              type="button"
              onClick={() => deleteOne(r)}
              disabled={deleting}
              title="Murojaatni butunlay o'chirish"
              className="inline-flex min-h-9 items-center rounded-full border border-red-200 px-3 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              🗑
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    // Full width on purpose: this table carries seven columns, and a narrow container only
    // moves the horizontal scrollbar inside the card on screens wide enough for the row.
    <div>
      <PageHeader
        title="Murojaatlar"
        subtitle={
          canManage
            ? "Barcha murojaatlar — kategoriya, holat va xodim bo'yicha filtrlang"
            : "Sizga ko'rinadigan barcha murojaatlar"
        }
      />

      {error && <ErrorBanner message={error} />}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.label_uz}
            </option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          {STATUS_FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        {canManage && (
          <select
            value={assigneeFilter}
            onChange={(e) => setAssigneeFilter(e.target.value)}
            className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
          >
            <option value="">Barcha RTM xodimlari</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name}
              </option>
            ))}
          </select>
        )}

        {filtersActive && (
          <button
            onClick={() => {
              setStatusFilter("");
              setCategoryFilter("");
              setAssigneeFilter("");
            }}
            className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-100"
          >
            ✖ Filtrni tozalash
          </button>
        )}

        <span className="text-sm text-slate-400">{items.length} ta murojaat</span>

        {isAdmin && items.length > 0 && (
          <label className="flex min-h-11 items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={() => setSelected(allSelected ? [] : items.map((r) => r.id))}
              className="h-4 w-4 accent-red-600"
            />
            Barchasini tanlash
          </label>
        )}
      </div>

      {isAdmin && selected.length > 0 && (
        // A bar rather than a always-visible button: the destructive action appears only
        // once something has actually been ticked, and says how many.
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <span className="text-sm text-red-800">
            <b>{selected.length}</b> ta murojaat tanlandi
          </span>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setSelected([])}
              className="min-h-11 rounded-lg border border-red-200 bg-white px-4 text-sm text-slate-600 hover:bg-slate-50"
            >
              Tanlovni bekor qilish
            </button>
            <button
              onClick={deleteSelected}
              disabled={deleting}
              className="min-h-11 rounded-lg bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleting ? "O'chirilmoqda..." : `🗑 ${selected.length} tasini o'chirish`}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <ResponsiveTable
          rows={items}
          columns={columns}
          rowKey={(r) => r.id}
          empty={
            statusFilter === "returned"
              ? "Qaytarib yuborilgan murojaat yo'q"
              : filtersActive
                ? "Bu filtrlarga mos murojaat topilmadi"
                : "Murojaatlar topilmadi"
          }
        />
      )}
    </div>
  );
}
