import { useState, type ReactNode } from "react";

export function ChartCard({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    // min-w-0 is load-bearing: a grid item defaults to min-width:auto, so a chart that
    // scrolls inside its own container would instead stretch this card and push the whole
    // page sideways on a phone.
    <section
      className={`min-w-0 rounded-xl border border-slate-200 bg-white p-5 ${className}`}
    >
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/**
 * A legend is present whenever there are two or more series, so identity is never carried
 * by colour alone. One series needs none — the title names it.
 */
export function Legend({ items }: { items: { label: string; color: string }[] }) {
  if (items.length < 2) return null;
  return (
    <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-xs text-slate-600">
          <span
            aria-hidden
            className="h-2.5 w-2.5 rounded-sm"
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function EmptyChart({ message = "Ma'lumot yo'q" }: { message?: string }) {
  return (
    <div className="py-10 text-center text-sm text-slate-400">{message}</div>
  );
}

interface TooltipState {
  x: number;
  y: number;
  content: ReactNode;
}

/**
 * Hover layer for a chart.
 *
 * Ships by default because an HTML chart *is* interactive: the labels on the marks give
 * the headline, and the tooltip gives the exact figure without turning every bar into a
 * number. Positioned against the wrapper rather than the page so it survives scrolling.
 */
export function useTooltip() {
  const [tip, setTip] = useState<TooltipState | null>(null);

  function bind(content: ReactNode) {
    return {
      onMouseMove: (e: React.MouseEvent) => {
        const box = e.currentTarget.closest("[data-chart-root]")?.getBoundingClientRect();
        if (!box) return;
        setTip({ x: e.clientX - box.left, y: e.clientY - box.top, content });
      },
      onMouseLeave: () => setTip(null),
    };
  }

  const node = tip ? (
    <div
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg"
      style={{ left: tip.x, top: tip.y - 8 }}
    >
      {tip.content}
    </div>
  ) : null;

  return { bind, node };
}
