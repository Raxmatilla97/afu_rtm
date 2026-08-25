import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { describeError } from "@/api/errors";
import { requestsApi } from "@/api/requests";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { StatusBadge } from "@/components/StatusBadge";
import { STATUS_LABELS, type RequestItem } from "@/types";

const FILTERS = [
  ["", "Barcha holatlar"],
  ["new", STATUS_LABELS.new],
  ["assigned", STATUS_LABELS.assigned],
  ["in_progress", STATUS_LABELS.in_progress],
  ["waiting", STATUS_LABELS.waiting],
  ["completed", STATUS_LABELS.completed],
  ["cancelled", STATUS_LABELS.cancelled],
] as const;

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

export function RequestsListPage() {
  const [items, setItems] = useState<RequestItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    requestsApi
      .list(statusFilter || undefined)
      .then((rows) => {
        setItems(rows);
        setError(null);
      })
      .catch((e) => setError(describeError(e)))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const columns: Column<RequestItem>[] = [
    {
      key: "number",
      header: "№",
      mobile: "title",
      cell: (r) => (
        <Link to={`/requests/${r.id}`} className="font-medium text-brand-700 hover:underline">
          {r.display_number}
        </Link>
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
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Murojaatlar"
        subtitle="Sizga ko'rinadigan barcha murojaatlar"
        action={
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm"
          >
            {FILTERS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        }
      />

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <ResponsiveTable
          rows={items}
          columns={columns}
          rowKey={(r) => r.id}
          empty="Murojaatlar topilmadi"
        />
      )}
    </div>
  );
}
