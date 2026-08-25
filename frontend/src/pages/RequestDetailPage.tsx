import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { requestsApi } from "@/api/requests";
import { describeError } from "@/api/errors";
import { employeesApi } from "@/api/reference";
import { AttachmentGrid } from "@/components/AttachmentView";
import { DeadlineBanner } from "@/components/DeadlineBanner";
import { RequestChat } from "@/components/RequestChat";
import { RequesterCard } from "@/components/RequesterCard";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import type {
  Employee,
  RequestAttachmentItem,
  RequestItem,
} from "@/types";

function dt(value: string | null): string {
  return value ? new Date(value).toLocaleString("uz-UZ") : "—";
}

export function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const requestId = Number(id);
  const { session, isAdmin } = useAuth();

  const [request, setRequest] = useState<RequestItem | null>(null);
  const [attachments, setAttachments] = useState<RequestAttachmentItem[]>([]);
  const [staffList, setStaffList] = useState<Employee[]>([]);
  const [assigneeIds, setAssigneeIds] = useState<number[]>([]);
  const [deadline, setDeadline] = useState("");
  const [completionNote, setCompletionNote] = useState("");
  const [ratingScore, setRatingScore] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Every mutating action goes through here.
   *
   * Each of these used to be a bare try/finally that reset `busy` and let the failure
   * disappear. Pressing "Tayinlash" against a request the server refused therefore looked
   * exactly like pressing a dead button — no change, no message, nothing to report.
   */
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  const myEmployeeId = session.kind === "employee" ? session.employee.id : null;
  const isStaff = session.kind === "employee" && session.employee.is_rtm_staff;
  // Panel admins, plus employees marked Boshliq or Admin. Assigning work — and taking
  // somebody off a job, which is the only place that is possible at all — belongs to them.
  const canManage =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);
  // Membership, not the primary column: a colleague who joined the job gets the same
  // actions as whoever picked it up first.
  const isStaffAssignee =
    myEmployeeId !== null && (request?.assignees ?? []).some((a) => a.employee_id === myEmployeeId);
  const isRequester = myEmployeeId !== null && myEmployeeId === request?.requester_employee_id;

  async function load() {
    // Messages are not fetched here: RequestChat owns them and polls for itself, so a
    // reload of the surrounding page never fights its own live updates.
    const [r, a] = await Promise.all([
      requestsApi.get(requestId),
      requestsApi.attachments(requestId),
    ]);
    setRequest(r);
    setAttachments(a);
    // Seed the admin form with who is actually on it, so re-saving does not silently
    // clear the team.
    setAssigneeIds(r.assignees.map((x) => x.employee_id));
  }

  useEffect(() => {
    load();
  }, [requestId]);

  useEffect(() => {
    if (canManage) employeesApi.list({ isRtmStaff: true }).then(setStaffList);
  }, [canManage]);

  function toggleAssignee(employeeId: number) {
    setAssigneeIds((current) =>
      current.includes(employeeId)
        ? current.filter((x) => x !== employeeId)
        : // Appended, not prepended: the first id is the primary, and re-picking somebody
          // should not quietly demote the lead the admin chose earlier.
          [...current, employeeId],
    );
  }

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (assigneeIds.length === 0) return;
    await run(async () => {
      await requestsApi.assign(
        requestId,
        assigneeIds,
        // datetime-local has no timezone, so the browser reads it as local time — which
        // is what the person typing it meant. toISOString converts to UTC for the server.
        deadline ? new Date(deadline).toISOString() : null,
      );
      await load();
    });
  }

  async function handleStatus(status: string) {
    await run(async () => {
      await requestsApi.updateStatus(requestId, status);
      await load();
    });
  }

  async function handleComplete(e: React.FormEvent) {
    e.preventDefault();
    await run(async () => {
      await requestsApi.complete(requestId, completionNote);
      setCompletionNote("");
      await load();
    });
  }

  async function handleRate(score: number) {
    await run(async () => {
      await requestsApi.rate(requestId, score);
      setRatingScore(score);
    });
  }

  if (!request) return <div className="text-slate-400">Yuklanmoqda...</div>;

  // Files posted inside the conversation are already rendered in their own bubble; the
  // gallery is for what came with the request itself, so it does not repeat them.
  const requestFiles = attachments.filter((a) => a.message_id === null);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">{request.display_number}</h1>
          <div className="text-sm text-slate-500">
            {request.category_label} · {request.source === "bot" ? "Telegram" : "Veb"}
          </div>
        </div>
        <StatusBadge status={request.status} />
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="space-y-6">
          <DeadlineBanner deadlineAt={request.deadline_at} status={request.status} />

          {request.requester && <RequesterCard requester={request.requester} />}

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-4 grid grid-cols-2 gap-4 text-sm">
              <Field label="Muddat" value={dt(request.deadline_at)} />
              <Field label="Yaratilgan" value={dt(request.created_at)} />
              <Field label="Bajarilgan" value={dt(request.completed_at)} />
            </div>
            <div className="mb-4 text-sm">
              <div className="text-slate-400">Bajaruvchilar</div>
              {request.assignees.length === 0 ? (
                <div className="font-medium text-slate-800">— hali hech kim olmadi</div>
              ) : (
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {request.assignees.map((a) => (
                    <span
                      key={a.employee_id}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        a.is_primary
                          ? "bg-brand-50 text-brand-700"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {a.is_primary ? "⭐ " : ""}
                      {a.full_name}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="mb-1 text-sm text-slate-400">Tavsif</div>
            <p className="whitespace-pre-wrap text-slate-800">{request.description}</p>
            {request.completion_note && (
              <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                <div className="mb-1 font-medium">Bajarilgan ish izohi</div>
                {request.completion_note}
              </div>
            )}
          </div>

          {requestFiles.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-3 text-sm font-medium text-slate-800">
                Biriktirilgan materiallar ({requestFiles.length})
              </div>
              <AttachmentGrid attachments={requestFiles} />
            </div>
          )}

          {canManage && (
            <form onSubmit={handleAssign} className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-1 font-medium text-slate-800">RTM xodimlariga tayinlash</div>
              <p className="mb-3 text-xs text-slate-400">
                Bir nechta xodimni tanlashingiz mumkin — birinchi tanlangani mas'ul
                hisoblanadi. Tanlovni olib tashlasangiz, xodim murojaatdan chiqariladi:
                <b> bu yagona joy</b>, chunki xodim o'zi olgan murojaatidan voz kecha olmaydi.
              </p>
              <div className="mb-3 flex flex-wrap gap-2">
                {staffList.map((s) => {
                  const picked = assigneeIds.includes(s.id);
                  const order = assigneeIds.indexOf(s.id);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => toggleAssignee(s.id)}
                      className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                        picked
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-slate-300 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {picked && order === 0 ? "⭐ " : picked ? "✓ " : ""}
                      {s.full_name}
                    </button>
                  );
                })}
              </div>
              <div className="flex flex-wrap gap-3">
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={busy || assigneeIds.length === 0}
                  className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  Tayinlash
                </button>
              </div>
              <p className="mt-2 text-xs text-slate-400">
                Yangi tayinlangan har bir xodimga Telegram orqali murojaat tafsilotlari va barcha
                materiallar yuboriladi. RTM guruhidagi kartochka ham yangilanadi.
              </p>
            </form>
          )}

          {isStaffAssignee && request.status !== "completed" && request.status !== "cancelled" && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-3 font-medium text-slate-800">Harakatlar</div>
              {request.status === "assigned" && (
                <button
                  onClick={() => handleStatus("in_progress")}
                  disabled={busy}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
                >
                  ▶️ Ishga boshladim
                </button>
              )}
              <form onSubmit={handleComplete} className="mt-4 flex gap-2">
                <input
                  value={completionNote}
                  onChange={(e) => setCompletionNote(e.target.value)}
                  placeholder="Bajarilgan ish izohi..."
                  required
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  ✅ Bajarildi
                </button>
              </form>
              <p className="mt-2 text-xs text-slate-400">
                Rasm yoki video bilan hisobot qoldirmoqchi bo'lsangiz, avval uni yozishmalarga
                yuboring.
              </p>
            </div>
          )}

          {isRequester && request.status === "completed" && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-2 font-medium text-slate-800">Xizmatni baholang</div>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => handleRate(n)}
                    disabled={busy}
                    className={`text-2xl ${n <= ratingScore ? "text-amber-400" : "text-slate-300"} hover:text-amber-400`}
                  >
                    ★
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sticky from lg up, where there is a second column to scroll past it. On a phone
            the chat is the next block down and takes a fixed slice of the viewport, so the
            composer stays reachable without scrolling the whole page first. */}
        <div className="h-[75vh] lg:sticky lg:top-8 lg:h-[calc(100vh-8rem)]">
          <RequestChat
            requestId={requestId}
            requesterEmployeeId={request.requester_employee_id}
            requesterName={request.requester_name || "Murojaatchi"}
            myEmployeeId={myEmployeeId}
            canWriteInternal={isAdmin || isStaff}
            canAttach={myEmployeeId !== null}
            onSent={load}
          />
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-slate-400">{label}</div>
      <div className="font-medium text-slate-800">{value}</div>
    </div>
  );
}
