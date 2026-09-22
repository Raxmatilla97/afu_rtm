import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { statsApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import { isOverdue, OverdueAlert } from "@/components/OverdueAlert";
import { PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import type { RequestItem, StatsSummary } from "@/types";

/** How many rows the home page shows before handing the reader over to /requests. */
const PREVIEW_LIMIT = 10;

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

export function DashboardPage() {
  const { session } = useAuth();
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [mine, setMine] = useState<RequestItem[]>([]);
  const [loading, setLoading] = useState(true);

  const myEmployeeId = session.kind === "employee" ? session.employee.id : null;
  const isStaff = session.kind === "employee" && session.employee.is_rtm_staff;

  useEffect(() => {
    statsApi.summary().then(setSummary).catch(() => setSummary(null));
    // The list endpoint already scopes to what the caller may see, so this is "my work"
    // for a staff member and "my requests" for everyone else.
    requestsApi
      .list()
      .then(setMine)
      .catch(() => setMine([]))
      .finally(() => setLoading(false));
  }, []);

  // Only jobs this person is actually on. A staff member's list also contains requests
  // they reported themselves, and being warned about a deadline somebody else owns would
  // train them to ignore the banner.
  const myWork =
    myEmployeeId === null
      ? mine
      : mine.filter((r) => r.assignees.some((a) => a.employee_id === myEmployeeId));

  // The list below is always personal, never a feed of everything. For RTM staff it is the
  // work they were given or picked up — completed ones included, since "what have I done"
  // is half the question — and for everybody else the requests they filed themselves.
  //
  // A panel admin has no employee identity and therefore files nothing, so they get an
  // empty list pointing at /requests rather than a global feed dressed up as "yours".
  const isEmployee = session.kind === "employee";
  const rows = isStaff ? myWork : isEmployee ? mine : [];
  const listTitle = isStaff
    ? "Sizga topshirilgan va siz bajargan murojaatlar"
    : "Siz yuborgan murojaatlar";
  const listEmpty = isStaff
    ? "Sizga hali murojaat topshirilmagan"
    : isEmployee
      ? "Siz hali murojaat yubormagansiz"
      : "Admin hisobi murojaat yubormaydi — barchasi «Murojaatlar» sahifasida.";

  const name = session.kind === "admin" ? session.admin.email : session.kind === "employee" ? session.employee.full_name : "";

  const cards = summary
    ? [
        { label: "Jami murojaatlar", value: summary.total_requests },
        { label: "Yangi", value: summary.new_count },
        { label: "Tayinlangan", value: summary.assigned_count },
        { label: "Jarayonda", value: summary.in_progress_count },
        { label: "Bajarilgan", value: summary.completed_count },
        { label: "Bekor qilingan", value: summary.cancelled_count },
      ]
    : [];

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
    { key: "status", header: "Holat", cell: (r) => <StatusBadge status={r.status} /> },
    {
      key: "deadline",
      header: "Muddat",
      cell: (r) => <span className="text-slate-500">{shortDate(r.deadline_at)}</span>,
    },
    {
      key: "created",
      header: "Yaratilgan",
      cell: (r) => <span className="text-slate-500">{shortDate(r.created_at)}</span>,
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (r) => (
        <div className="flex justify-end md:justify-start">
          <Link
            to={`/requests/${r.id}`}
            className="inline-flex min-h-9 items-center rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
          >
            👁 Ko'rish
          </Link>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={`Xush kelibsiz, ${name}`}
        subtitle="RTM murojaatlar tizimi bosh sahifasi"
      />

      <OverdueAlert requests={myWork} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-2xl font-bold text-brand-700">{c.value}</div>
            <div className="text-xs text-slate-500">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link to="/requests" className="inline-flex min-h-11 items-center rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700">
          Murojaatlarni ko'rish
        </Link>
        {session.kind === "employee" && (
          <Link to="/requests/new" className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50">
            {session.employee.can_file_managed_request ? "👑 Yangi topshiriq" : "Yangi murojaat"}
          </Link>
        )}
      </div>

      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {listTitle}
              {rows.length > 0 && (
                <span className="ml-2 text-sm font-normal text-slate-400">{rows.length} ta</span>
              )}
            </h2>
            <p className="text-xs text-slate-400">
              {isStaff
                ? "Ochish uchun «Ko'rish» tugmasini bosing — amallar murojaat sahifasida."
                : "Faqat ko'rish rejimi — murojaatga o'zgartirish kirita olmaysiz."}
            </p>
          </div>
          {/* Only when something is actually hidden — a "see all" next to a complete list
              is a dead end the reader has to click to find out about. */}
          {rows.length > PREVIEW_LIMIT && (
            <Link to="/requests" className="text-sm font-medium text-brand-700 hover:underline">
              Barchasini ko'rish →
            </Link>
          )}
        </div>

        {loading ? (
          <div className="text-slate-400">Yuklanmoqda...</div>
        ) : (
          // rowClass: the banner above names the late jobs, and tinting them here is what
          // lets the reader find those rows again without re-reading every date.
          <ResponsiveTable
            rows={rows.slice(0, PREVIEW_LIMIT)}
            columns={columns}
            rowKey={(r) => r.id}
            empty={listEmpty}
            rowClass={(r) => (isOverdue(r) ? "bg-red-50/60" : "")}
          />
        )}
      </section>
    </div>
  );
}
