import { useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { statsApi } from "@/api/reference";
import { ChartCard } from "@/components/charts/Chart";
import { ColumnChart } from "@/components/charts/ColumnChart";
import { HBarChart } from "@/components/charts/HBarChart";
import { ShareBar } from "@/components/charts/ShareBar";
import { SEQUENTIAL, SERIES, STATUS, STATUS_ORDER } from "@/components/charts/palette";
import { STATUS_LABELS, type StatsOverview } from "@/types";

const MONTH_NAMES = [
  "yan", "fev", "mar", "apr", "may", "iyn",
  "iyl", "avg", "sen", "okt", "noy", "dek",
];

function monthLabel(key: string): string {
  const [year, month] = key.split("-");
  return `${MONTH_NAMES[Number(month) - 1] ?? month} ${year.slice(2)}`;
}

/** Hours are the wire format; nobody reads "73.4 soat". */
function duration(hours: number | null): string {
  if (hours === null) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} daq`;
  if (hours < 48) return `${hours.toFixed(1)} soat`;
  return `${(hours / 24).toFixed(1)} kun`;
}

export function StatsPage() {
  const [data, setData] = useState<StatsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    statsApi
      .overview()
      .then(setData)
      .catch((e) => setError(describeError(e)));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!data) return <div className="text-slate-400">Yuklanmoqda...</div>;

  const { summary, resolution } = data;
  const open = summary.new_count + summary.assigned_count + summary.in_progress_count;
  const completionRate = summary.total_requests
    ? Math.round((summary.completed_count / summary.total_requests) * 100)
    : 0;
  const deadlineTotal = resolution.on_time + resolution.late;
  const onTimeRate = deadlineTotal ? Math.round((resolution.on_time / deadlineTotal) * 100) : null;

  const statusShares = STATUS_ORDER.map((status, index) => ({
    label: STATUS_LABELS[status],
    value: {
      new: summary.new_count,
      assigned: summary.assigned_count,
      in_progress: summary.in_progress_count,
      completed: summary.completed_count,
      cancelled: summary.cancelled_count,
    }[status],
    color: SERIES[index],
  }));

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Statistika</h1>
          <p className="text-sm text-slate-500">
            Sizga ko'rinadigan murojaatlar bo'yicha umumiy manzara
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-white"
        >
          {showTable ? "📊 Diagrammalar" : "📋 Jadval ko'rinishi"}
        </button>
      </div>

      {/* Headline numbers, not charts: a single value has no shape to show. */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Tile label="Jami murojaat" value={summary.total_requests} />
        <Tile label="Ochiq" value={open} accent={SERIES[0]} />
        <Tile
          label="Bajarilgan"
          value={summary.completed_count}
          note={`${completionRate}%`}
          accent={STATUS.good}
        />
        <Tile
          label="Muddati o'tgan"
          value={data.open_overdue}
          accent={data.open_overdue > 0 ? STATUS.critical : undefined}
          icon={data.open_overdue > 0 ? "🔴" : undefined}
        />
        <Tile
          label="O'rtacha baho"
          value={data.average_rating ? data.average_rating.toFixed(2) : "—"}
          note={data.rating_count ? `${data.rating_count} ta baho` : undefined}
          accent={STATUS.warning}
          icon="⭐"
        />
        <Tile
          label="Median bajarish"
          value={duration(resolution.median_hours)}
          note={`o'rtacha ${duration(resolution.average_hours)}`}
        />
      </div>

      {showTable ? (
        <TableView data={data} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <ChartCard
            title="Holatlar bo'yicha taqsimot"
            subtitle={`Jami ${summary.total_requests} ta murojaat`}
            className="lg:col-span-2"
          >
            <ShareBar shares={statusShares} />
          </ChartCard>

          <ChartCard
            title="Oylar kesimida"
            subtitle="Kelgan va bajarilgan murojaatlar — farq navbat o'sayotganini ko'rsatadi"
            className="lg:col-span-2"
          >
            <ColumnChart
              groups={data.monthly.map((m) => ({
                label: monthLabel(m.month),
                values: [m.created, m.completed],
              }))}
              series={[
                { label: "Kelgan", color: SERIES[0] },
                { label: "Bajarilgan", color: SERIES[2] },
              ]}
              emptyMessage="Hali murojaatlar yo'q"
            />
          </ChartCard>

          <ChartCard title="Kategoriyalar bo'yicha" subtitle="Eng ko'p uchraydigan muammolar">
            <HBarChart
              rows={data.by_category.map((c) => ({
                label: c.label,
                values: [c.total],
                note: c.total ? `${Math.round((c.completed / c.total) * 100)}% bajarilgan` : undefined,
              }))}
              emptyMessage="Kategoriya ma'lumoti yo'q"
            />
          </ChartCard>

          <ChartCard
            title="Baholar"
            subtitle={
              data.rating_count
                ? `${data.rating_count} ta baho · o'rtacha ${data.average_rating?.toFixed(2)}`
                : "Hali baho qo'yilmagan"
            }
          >
            <HBarChart
              rows={[...data.ratings].reverse().map((r) => ({
                label: "⭐".repeat(r.score),
                values: [r.count],
              }))}
              emptyMessage="Hali baho qo'yilmagan"
            />
          </ChartCard>

          <ChartCard
            title="Muddatga rioya"
            subtitle="Muddat belgilangan va yakunlangan murojaatlar"
          >
            {deadlineTotal === 0 ? (
              <p className="py-10 text-center text-sm text-slate-400">
                Muddat belgilangan yakunlangan murojaat yo'q
              </p>
            ) : (
              <>
                <div className="mb-4 text-3xl font-bold tabular-nums text-slate-900">
                  {onTimeRate}%
                  <span className="ml-2 text-sm font-normal text-slate-500">o'z vaqtida</span>
                </div>
                <ShareBar
                  shares={[
                    { label: "✅ O'z vaqtida", value: resolution.on_time, color: STATUS.good },
                    { label: "🔴 Kechikkan", value: resolution.late, color: STATUS.critical },
                  ]}
                />
              </>
            )}
          </ChartCard>

          <ChartCard title="Bajarish vaqti" subtitle="Yakunlangan murojaatlar bo'yicha">
            <dl className="space-y-3">
              <Metric label="Eng tez" value={duration(resolution.fastest_hours)} />
              <Metric label="Median" value={duration(resolution.median_hours)} emphasis />
              <Metric label="O'rtacha" value={duration(resolution.average_hours)} />
              <Metric label="Eng uzun" value={duration(resolution.slowest_hours)} />
            </dl>
            <p className="mt-4 text-xs text-slate-400">
              Median o'rtachadan ishonchliroq: bayram kunlari ochiq qolgan bitta murojaat
              o'rtachani hech qachon bo'lmagan qiymatga tortadi.
            </p>
          </ChartCard>

          {data.staff_load.length > 0 && (
            <ChartCard
              title="RTM xodimlari yuklamasi"
              subtitle="Ochiq va bajarilgan topshiriqlar"
              className="lg:col-span-2"
            >
              <HBarChart
                rows={data.staff_load.map((s) => ({
                  label: s.full_name,
                  values: [s.open_count, s.completed_count],
                  note: s.average_score ? `⭐ ${s.average_score.toFixed(1)}` : undefined,
                }))}
                series={[
                  { label: "Ochiq", color: SERIES[0] },
                  { label: "Bajarilgan", color: SERIES[2] },
                ]}
              />
            </ChartCard>
          )}
        </div>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  note,
  accent,
  icon,
}: {
  label: string;
  value: number | string;
  note?: string;
  accent?: string;
  icon?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div
        className="text-2xl font-bold tabular-nums"
        style={{ color: accent ?? SEQUENTIAL }}
      >
        {icon && <span className="mr-1 text-lg">{icon}</span>}
        {value}
      </div>
      <div className="text-xs text-slate-500">{label}</div>
      {note && <div className="mt-0.5 text-[11px] text-slate-400">{note}</div>}
    </div>
  );
}

function Metric({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-slate-100 pb-2 last:border-0">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd
        className={`tabular-nums ${
          emphasis ? "text-lg font-bold text-slate-900" : "font-medium text-slate-700"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * The same numbers as text.
 *
 * Required, not a nicety: three of the chart hues sit below 3:1 against the card
 * background, and a table view is one of the two accepted forms of relief for that. It is
 * also the only way to read exact figures with a screen reader.
 */
function TableView({ data }: { data: StatsOverview }) {
  return (
    <div className="space-y-6">
      <Table
        title="Holatlar"
        head={["Holat", "Soni"]}
        rows={STATUS_ORDER.map((status) => [
          STATUS_LABELS[status],
          String(
            {
              new: data.summary.new_count,
              assigned: data.summary.assigned_count,
              in_progress: data.summary.in_progress_count,
              completed: data.summary.completed_count,
              cancelled: data.summary.cancelled_count,
            }[status],
          ),
        ])}
      />
      <Table
        title="Oylar kesimida"
        head={["Oy", "Kelgan", "Bajarilgan"]}
        rows={data.monthly.map((m) => [monthLabel(m.month), String(m.created), String(m.completed)])}
      />
      <Table
        title="Kategoriyalar"
        head={["Kategoriya", "Jami", "Bajarilgan"]}
        rows={data.by_category.map((c) => [c.label, String(c.total), String(c.completed)])}
      />
      <Table
        title="Baholar"
        head={["Baho", "Soni"]}
        rows={[...data.ratings].reverse().map((r) => [`${r.score} / 5`, String(r.count)])}
      />
      <Table
        title="RTM xodimlari"
        head={["Xodim", "Ochiq", "Bajarilgan", "O'rtacha baho"]}
        rows={data.staff_load.map((s) => [
          s.full_name,
          String(s.open_count),
          String(s.completed_count),
          s.average_score ? s.average_score.toFixed(2) : "—",
        ])}
      />
    </div>
  );
}

function Table({
  title,
  head,
  rows,
}: {
  title: string;
  head: string[];
  rows: string[][];
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-semibold text-slate-800">
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="px-4 py-4 text-sm text-slate-400">Ma'lumot yo'q</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              {head.map((h, i) => (
                <th key={h} className={`px-4 py-2 ${i > 0 ? "text-right" : ""}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[0]} className="border-t border-slate-100">
                {row.map((cell, i) => (
                  <td
                    key={i}
                    className={`px-4 py-2 ${i > 0 ? "text-right tabular-nums" : "font-medium"}`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
