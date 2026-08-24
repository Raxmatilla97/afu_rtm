import type { RequesterCard as RequesterCardData } from "@/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/**
 * Who reported the problem.
 *
 * Deliberately shows the ways to reach them, not just the name: the person picking the
 * request up almost always needs to call or find the reporter, and hunting for that in the
 * employees list was the most common reason to leave this page.
 */
export function RequesterCard({ requester }: { requester: RequesterCardData }) {
  const photo = requester.image_local_path ? `/media/${requester.image_local_path}` : null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 text-xs font-medium uppercase tracking-wide text-slate-400">
        Murojaatchi
      </div>
      <div className="flex items-center gap-3">
        {photo ? (
          <img
            src={photo}
            alt={requester.full_name}
            className="h-14 w-14 rounded-full border border-slate-200 object-cover"
          />
        ) : (
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-lg font-semibold text-brand-700">
            {initials(requester.full_name)}
          </div>
        )}
        <div className="min-w-0">
          <div className="truncate font-semibold text-slate-900">{requester.full_name}</div>
          {requester.department_name && (
            <div className="truncate text-sm text-slate-500">{requester.department_name}</div>
          )}
        </div>
      </div>

      <dl className="mt-4 space-y-2 text-sm">
        {requester.employee_id_number && (
          <Row label="Xodim ID" value={requester.employee_id_number} />
        )}
        {requester.phone_number && (
          <Row
            label="Telefon"
            value={
              <a className="text-brand-600 hover:underline" href={`tel:${requester.phone_number}`}>
                {requester.phone_number}
              </a>
            }
          />
        )}
        {requester.telegram_username && (
          <Row
            label="Telegram"
            value={
              <a
                className="text-brand-600 hover:underline"
                href={`https://t.me/${requester.telegram_username}`}
                target="_blank"
                rel="noreferrer"
              >
                @{requester.telegram_username}
              </a>
            }
          />
        )}
      </dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-slate-400">{label}</dt>
      <dd className="truncate text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}
