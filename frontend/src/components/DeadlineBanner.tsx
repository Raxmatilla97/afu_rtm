import { useEffect, useState } from "react";

interface Props {
  deadlineAt: string | null;
  status: string;
}

const CLOSED = new Set(["completed", "cancelled", "returned"]);
/** Below this the banner turns amber: a deadline inside one working day is a plan, not a note. */
const URGENT_MS = 24 * 60 * 60 * 1000;

function parts(ms: number) {
  const total = Math.floor(Math.abs(ms) / 1000);
  return {
    days: Math.floor(total / 86400),
    hours: Math.floor((total % 86400) / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}

/**
 * The deadline, counting down in real time.
 *
 * Deliberately large and impossible to skim past. A deadline printed as a date in a table
 * of other dates carries no urgency; the same deadline as a clock running towards zero is
 * the one thing on the page that keeps changing, and that is what gets it noticed.
 */
export function DeadlineBanner({ deadlineAt, status }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!deadlineAt || CLOSED.has(status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [deadlineAt, status]);

  if (!deadlineAt || CLOSED.has(status)) return null;

  const target = new Date(deadlineAt).getTime();
  const remaining = target - now;
  const overdue = remaining < 0;
  const urgent = !overdue && remaining < URGENT_MS;
  const { days, hours, minutes, seconds } = parts(remaining);

  const tone = overdue
    ? {
        wrap: "border-red-300 bg-red-50",
        title: "text-red-800",
        digits: "text-red-700",
        sub: "text-red-600",
      }
    : urgent
      ? {
          wrap: "border-amber-300 bg-amber-50",
          title: "text-amber-800",
          digits: "text-amber-700",
          sub: "text-amber-600",
        }
      : {
          wrap: "border-brand-100 bg-brand-50",
          title: "text-brand-700",
          digits: "text-brand-700",
          sub: "text-slate-500",
        };

  return (
    <div className={`rounded-xl border p-5 ${tone.wrap}`} role={overdue ? "alert" : undefined}>
      <div className={`mb-3 flex items-center gap-2 text-sm font-semibold ${tone.title}`}>
        <span className="text-lg">{overdue ? "🔴" : urgent ? "⚠️" : "⏰"}</span>
        {overdue
          ? "MUDDAT O'TIB KETDI"
          : urgent
            ? "Muddat yaqinlashmoqda"
            : "Bajarish muddati"}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        {days > 0 && <Cell value={days} label="kun" className={tone.digits} />}
        <Cell value={hours} label="soat" className={tone.digits} />
        <Cell value={minutes} label="daqiqa" className={tone.digits} />
        <Cell value={seconds} label="soniya" className={tone.digits} />
      </div>

      <div className={`mt-3 text-xs ${tone.sub}`}>
        {overdue ? "Kechikish · " : "Qolgan vaqt · "}
        muddat: {new Date(deadlineAt).toLocaleString("uz-UZ")}
      </div>

      {overdue && (
        <p className="mt-3 rounded-lg bg-red-100 px-3 py-2 text-sm text-red-800">
          Bu murojaat belgilangan muddatda bajarilmadi. Iltimos, zudlik bilan yakunlang yoki
          murojaatchiga holat haqida xabar bering.
        </p>
      )}
    </div>
  );
}

function Cell({ value, label, className }: { value: number; label: string; className: string }) {
  return (
    <div className="text-center">
      <div
        className={`min-w-[3.25rem] rounded-lg bg-white/70 px-2 py-1 font-mono text-3xl font-bold tabular-nums ${className}`}
      >
        {String(value).padStart(2, "0")}
      </div>
      <div className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}
