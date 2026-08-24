import { EmptyChart, Legend, useTooltip } from "@/components/charts/Chart";

export interface ColumnGroup {
  label: string;
  values: number[];
}

interface Props {
  groups: ColumnGroup[];
  series: { label: string; color: string }[];
  height?: number;
  emptyMessage?: string;
}

/** Recessive gridlines — enough to read a height against, not enough to compete with it. */
const GRID_STEPS = 4;

/**
 * Grouped columns over time.
 *
 * Both series count requests, so they share one axis — the whole point is to read the gap
 * between them, which is the queue growing or shrinking. Two scales would make that gap
 * mean nothing at all.
 *
 * Divs rather than SVG, for the same reason as the horizontal bars: a scaled viewBox
 * rescales the axis labels with the geometry.
 */
export function ColumnChart({ groups, series, height = 200, emptyMessage }: Props) {
  const { bind, node } = useTooltip();
  if (groups.length === 0) return <EmptyChart message={emptyMessage} />;

  const max = Math.max(1, ...groups.flatMap((g) => g.values));

  return (
    <div data-chart-root className="relative">
      <Legend items={series} />

      <div className="overflow-x-auto pb-1">
        <div style={{ minWidth: Math.max(300, groups.length * 54) }}>
          <div className="relative" style={{ height }}>
            {Array.from({ length: GRID_STEPS + 1 }, (_, i) => (
              <div
                key={i}
                aria-hidden
                className="absolute inset-x-0 border-t border-slate-200"
                style={{ top: `${(i / GRID_STEPS) * 100}%` }}
              />
            ))}

            <div className="absolute inset-0 flex items-end gap-2">
              {groups.map((group) => (
                <div key={group.label} className="flex h-full flex-1 items-end gap-[2px]">
                  {group.values.map((value, seriesIndex) => (
                    <div
                      key={seriesIndex}
                      className="flex h-full flex-1 items-end"
                      {...bind(
                        <span>
                          {group.label} · {series[seriesIndex].label}: <b>{value}</b>
                        </span>,
                      )}
                    >
                      {/* Rounded top, square foot: the bar is anchored to the baseline and
                          must not look as though it floats above it. */}
                      <div
                        className="w-full rounded-t-sm"
                        style={{
                          height: value > 0 ? `${Math.max(2, (value / max) * 100)}%` : 1,
                          background: series[seriesIndex].color,
                        }}
                      />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="mt-1.5 flex gap-2">
            {groups.map((group) => (
              <div
                key={group.label}
                className="flex-1 text-center text-[11px] text-slate-400"
              >
                {group.label}
              </div>
            ))}
          </div>
        </div>
      </div>
      {node}
    </div>
  );
}
