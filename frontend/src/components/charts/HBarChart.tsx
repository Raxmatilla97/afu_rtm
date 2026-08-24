import { EmptyChart, Legend, useTooltip } from "@/components/charts/Chart";
import { SEQUENTIAL } from "@/components/charts/palette";

export interface HBarRow {
  label: string;
  /** One value per series. A single-element array draws a plain bar. */
  values: number[];
  /** Shown at the end of the row — a rating, a share, whatever the row earns. */
  note?: string;
}

interface Props {
  rows: HBarRow[];
  series?: { label: string; color: string }[];
  emptyMessage?: string;
  formatValue?: (value: number) => string;
}

/**
 * Horizontal bars — the safe default for ranked magnitude with text labels.
 *
 * Horizontal rather than vertical because the labels are names: rotated or truncated
 * category labels are the commonest way a bar chart stops being readable.
 *
 * Built from divs rather than SVG on purpose. A scaled `viewBox` resizes the *text* along
 * with the geometry, so the same chart renders 9px labels in one column and 18px in
 * another; percentage widths keep the bars responsive while the type stays at its real
 * size.
 */
export function HBarChart({
  rows,
  series,
  emptyMessage,
  formatValue = (v) => String(v),
}: Props) {
  const { bind, node } = useTooltip();
  if (rows.length === 0) return <EmptyChart message={emptyMessage} />;

  const seriesDefs = series ?? [{ label: "", color: SEQUENTIAL }];
  const max = Math.max(1, ...rows.flatMap((r) => r.values));

  return (
    <div data-chart-root className="relative">
      <Legend items={seriesDefs.filter((s) => s.label)} />

      <ul className="space-y-3">
        {rows.map((row) => (
          <li key={row.label}>
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="truncate text-xs font-medium text-slate-700">{row.label}</span>
              {row.note && (
                <span className="shrink-0 text-xs text-slate-400">{row.note}</span>
              )}
            </div>

            {/* gap-[2px] is the surface spacer the mark spec asks for between the bars of
                one group — without it two similar hues read as a single mark. */}
            <div className="flex flex-col gap-[2px]">
              {row.values.map((value, seriesIndex) => (
                <div
                  key={seriesIndex}
                  className="flex items-center gap-2"
                  {...bind(
                    <span>
                      {row.label}
                      {seriesDefs[seriesIndex].label
                        ? ` · ${seriesDefs[seriesIndex].label}`
                        : ""}
                      : <b>{formatValue(value)}</b>
                    </span>,
                  )}
                >
                  <div className="h-3.5 flex-1 rounded-sm bg-slate-100">
                    <div
                      className="h-full rounded-sm"
                      style={{
                        // A present-but-tiny value still gets a visible sliver, so "1"
                        // never renders as an empty track indistinguishable from zero.
                        width: value > 0 ? `${Math.max(2, (value / max) * 100)}%` : 0,
                        background: seriesDefs[seriesIndex].color,
                      }}
                    />
                  </div>
                  <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums text-slate-800">
                    {formatValue(value)}
                  </span>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {node}
    </div>
  );
}
