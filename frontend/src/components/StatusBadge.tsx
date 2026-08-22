import { STATUS_LABELS } from "@/types";

const COLORS: Record<string, string> = {
  new: "bg-slate-100 text-slate-700",
  assigned: "bg-amber-100 text-amber-800",
  in_progress: "bg-blue-100 text-blue-800",
  completed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${COLORS[status] || "bg-slate-100 text-slate-700"}`}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}
