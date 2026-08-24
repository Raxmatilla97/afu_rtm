import { EmptyChart, useTooltip } from "@/components/charts/Chart";

export interface Share {
  label: string;
  value: number;
  color: string;
}

/**
 * Part-to-whole as one horizontal bar, not a donut.
 *
 * A donut asks the reader to compare angles, which people are measurably bad at; a single
 * stacked bar asks them to compare lengths along a shared baseline, which they are good
 * at. It also degrades gracefully to five slices where a donut turns into confetti.
 */
export function ShareBar({ shares, emptyMessage }: { shares: Share[]; emptyMessage?: string }) {
  const { bind, node } = useTooltip();
  const total = shares.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) return <EmptyChart message={emptyMessage} />;

  const visible = shares.filter((s) => s.value > 0);

  return (
    <div data-chart-root className="relative">
      {/* gap-[2px] is the surface spacer between segments — without it two adjacent
          slices of similar hue read as one. */}
      <div className="flex h-7 w-full gap-[2px] overflow-hidden rounded-lg">
        {visible.map((share) => (
          <div
            key={share.label}
            className="h-full first:rounded-l-lg last:rounded-r-lg"
            style={{
              width: `${(share.value / total) * 100}%`,
              background: share.color,
            }}
            {...bind(
              <span>
                {share.label}: <b>{share.value}</b> ({Math.round((share.value / total) * 100)}%)
              </span>,
            )}
          />
        ))}
      </div>

      {/* Every slice is labelled: three of the five hues sit below 3:1 against white, and
          visible labels are the relief that makes that legal. */}
      {/* Wrapping items with their own width rather than a stretched grid: in a wide card
          a grid column pushes the count to the far edge, leaving a run of empty space
          between a label and the number it belongs to. */}
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5">
        {shares.map((share) => (
          <li
            key={share.label}
            className="flex min-w-[9rem] flex-1 items-center gap-2 text-xs sm:flex-none"
          >
            <span
              aria-hidden
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: share.color }}
            />
            <span className="truncate text-slate-600">{share.label}</span>
            <span className="ml-auto font-semibold tabular-nums text-slate-800">
              {share.value}
            </span>
          </li>
        ))}
      </ul>
      {node}
    </div>
  );
}
