import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  /** How the cell renders in the desktop table. */
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  /**
   * Where this column goes on a phone. `title` is the card's headline, `meta` sits under
   * it as a small line, `hidden` is dropped, and everything else becomes a labelled row.
   */
  mobile?: "title" | "meta" | "row" | "hidden";
  className?: string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  empty?: ReactNode;
  /** Extra classes on the desktop row / mobile card, e.g. to tint a low-stock line. */
  rowClass?: (row: T) => string;
}

/**
 * One column definition, two layouts.
 *
 * A table with six columns is unusable on a phone: it either scrolls sideways, which hides
 * the column that mattered, or it squeezes until every cell wraps to four lines. So below
 * `md` each row becomes a card — the headline column as its title, the rest as labelled
 * lines — and from `md` up it is an ordinary table.
 *
 * Defining that once per page rather than writing the markup twice is what stops the two
 * from drifting: a column added to the table and forgotten in the card list is invisible
 * to every phone user.
 */
export function ResponsiveTable<T>({ rows, columns, rowKey, empty, rowClass }: Props<T>) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
        {empty ?? "Ma'lumot yo'q"}
      </div>
    );
  }

  const titleColumn = columns.find((c) => c.mobile === "title") ?? columns[0];
  const metaColumns = columns.filter((c) => c.mobile === "meta");
  const rowColumns = columns.filter(
    (c) => c !== titleColumn && c.mobile !== "meta" && c.mobile !== "hidden",
  );

  return (
    <>
      {/* Cards below md. */}
      <ul className="space-y-3 md:hidden">
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className={`rounded-xl border border-slate-200 bg-white p-4 ${rowClass?.(row) ?? ""}`}
          >
            <div className="font-medium text-slate-900">{titleColumn.cell(row)}</div>
            {metaColumns.length > 0 && (
              <div className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-slate-500">
                {metaColumns.map((c) => (
                  <span key={c.key}>{c.cell(row)}</span>
                ))}
              </div>
            )}
            {rowColumns.length > 0 && (
              <dl className="mt-3 space-y-1.5 text-sm">
                {rowColumns.map((c) => (
                  <div key={c.key} className="flex items-start justify-between gap-3">
                    <dt className="shrink-0 text-xs text-slate-400">{c.header}</dt>
                    <dd className="min-w-0 text-right text-slate-700">{c.cell(row)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>

      {/* Table from md up. The scroller keeps a wide table inside the card. */}
      <div className="hidden overflow-x-auto rounded-xl border border-slate-200 bg-white md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              {columns
                .filter((c) => c.mobile !== "hidden" || true)
                .map((c) => (
                  <th
                    key={c.key}
                    className={`px-4 py-3 ${c.align === "right" ? "text-right" : ""}`}
                  >
                    {c.header}
                  </th>
                ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${
                  rowClass?.(row) ?? ""
                }`}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={`px-4 py-3 ${c.align === "right" ? "text-right" : ""} ${
                      c.className ?? ""
                    }`}
                  >
                    {c.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
