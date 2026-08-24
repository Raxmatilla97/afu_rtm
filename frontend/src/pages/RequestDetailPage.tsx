import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { requestsApi } from "@/api/requests";
import { employeesApi } from "@/api/reference";
import { AttachmentGrid } from "@/components/AttachmentView";
import { RequestChat } from "@/components/RequestChat";
import { RequesterCard } from "@/components/RequesterCard";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import type {
  Employee,
  RequestAttachmentItem,
  RequestItem,
  RequestMessageItem,
} from "@/types";

function dt(value: string | null): string {
  return value ? new Date(value).toLocaleString("uz-UZ") : "—";
}

export function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const requestId = Number(id);
  const { session } = useAuth();

  const [request, setRequest] = useState<RequestItem | null>(null);
  const [messages, setMessages] = useState<RequestMessageItem[]>([]);
  const [attachments, setAttachments] = useState<RequestAttachmentItem[]>([]);
  const [staffList, setStaffList] = useState<Employee[]>([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [deadline, setDeadline] = useState("");
  const [completionNote, setCompletionNote] = useState("");
  const [ratingScore, setRatingScore] = useState(0);
  const [busy, setBusy] = useState(false);

  const isAdmin = session.kind === "admin";
  const myEmployeeId = session.kind === "employee" ? session.employee.id : null;
  const isStaff = session.kind === "employee" && session.employee.is_rtm_staff;
  const isStaffAssignee = myEmployeeId !== null && myEmployeeId === request?.assigned_to_employee_id;
  const isRequester = myEmployeeId !== null && myEmployeeId === request?.requester_employee_id;

  async function load() {
    const [r, m, a] = await Promise.all([
      requestsApi.get(requestId),
      requestsApi.messages(requestId),
      requestsApi.attachments(requestId),
    ]);
    setRequest(r);
    setMessages(m);
    setAttachments(a);
  }

  useEffect(() => {
    load();
  }, [requestId]);

  useEffect(() => {
    if (isAdmin) employeesApi.list({ isRtmStaff: true }).then(setStaffList);
  }, [isAdmin]);

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (!assigneeId) return;
    setBusy(true);
    try {
      await requestsApi.assign(
        requestId,
        Number(assigneeId),
        deadline ? new Date(deadline).toISOString() : null,
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function handleStatus(status: string) {
    setBusy(true);
    try {
      await requestsApi.updateStatus(requestId, status);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function handleComplete(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await requestsApi.complete(requestId, completionNote);
      setCompletionNote("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function handleRate(score: number) {
    setBusy(true);
    try {
      await requestsApi.rate(requestId, score);
      setRatingScore(score);
    } finally {
      setBusy(false);
    }
  }

  if (!request) return <div className="text-slate-400">Yuklanmoqda...</div>;

  // Files posted inside the conversation are already rendered in their own bubble; the
  // gallery is for what came with the request itself, so it does not repeat them.
  const requestFiles = attachments.filter((a) => a.message_id === null);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{request.display_number}</h1>
          <div className="text-sm text-slate-500">
            {request.category_label} · {request.source === "bot" ? "Telegram" : "Veb"}
          </div>
        </div>
        <StatusBadge status={request.status} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="space-y-6">
          {request.requester && <RequesterCard requester={request.requester} />}

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-4 grid grid-cols-2 gap-4 text-sm">
              <Field label="Tayinlangan" value={request.assigned_to_name || "—"} />
              <Field label="Muddat" value={dt(request.deadline_at)} />
              <Field label="Yaratilgan" value={dt(request.created_at)} />
              <Field label="Bajarilgan" value={dt(request.completed_at)} />
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

          {isAdmin && (
            <form onSubmit={handleAssign} className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-3 font-medium text-slate-800">RTM xodimiga tayinlash</div>
              <div className="flex flex-wrap gap-3">
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="">Xodimni tanlang</option>
                  {staffList.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.full_name}
                    </option>
                  ))}
                </select>
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={busy || !assigneeId}
                  className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  Tayinlash
                </button>
              </div>
              <p className="mt-2 text-xs text-slate-400">
                Tayinlangan xodimga Telegram orqali murojaat tafsilotlari va barcha materiallar
                yuboriladi.
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

        {/* Sticky so the conversation stays in view while the details column scrolls. */}
        <div className="h-[calc(100vh-10rem)] lg:sticky lg:top-8">
          <RequestChat
            requestId={requestId}
            messages={messages}
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
