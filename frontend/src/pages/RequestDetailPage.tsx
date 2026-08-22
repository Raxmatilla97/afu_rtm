import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { requestsApi } from "@/api/requests";
import { employeesApi } from "@/api/reference";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import type { Employee, RequestItem, RequestMessageItem } from "@/types";

export function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const requestId = Number(id);
  const { session } = useAuth();

  const [request, setRequest] = useState<RequestItem | null>(null);
  const [messages, setMessages] = useState<RequestMessageItem[]>([]);
  const [staffList, setStaffList] = useState<Employee[]>([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [deadline, setDeadline] = useState("");
  const [messageBody, setMessageBody] = useState("");
  const [completionNote, setCompletionNote] = useState("");
  const [ratingScore, setRatingScore] = useState(0);
  const [busy, setBusy] = useState(false);

  const isAdmin = session.kind === "admin";
  const isStaffAssignee = session.kind === "employee" && session.employee.id === request?.assigned_to_employee_id;
  const isRequester = session.kind === "employee" && session.employee.id === request?.requester_employee_id;

  async function load() {
    const [r, m] = await Promise.all([requestsApi.get(requestId), requestsApi.messages(requestId)]);
    setRequest(r);
    setMessages(m);
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
      await requestsApi.assign(requestId, Number(assigneeId), deadline ? new Date(deadline).toISOString() : null);
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

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!messageBody.trim()) return;
    setBusy(true);
    try {
      await requestsApi.postMessage(requestId, messageBody, "to_requester");
      setMessageBody("");
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

  return (
    <div className="max-w-3xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{request.display_number}</h1>
          <div className="text-sm text-slate-500">{request.category_label}</div>
        </div>
        <StatusBadge status={request.status} />
      </div>

      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-slate-400">Murojaatchi</div>
            <div className="font-medium">{request.requester_name}</div>
          </div>
          <div>
            <div className="text-slate-400">Tayinlangan</div>
            <div className="font-medium">{request.assigned_to_name || "-"}</div>
          </div>
          <div>
            <div className="text-slate-400">Muddat</div>
            <div className="font-medium">{request.deadline_at ? new Date(request.deadline_at).toLocaleString("uz-UZ") : "-"}</div>
          </div>
          <div>
            <div className="text-slate-400">Yaratilgan</div>
            <div className="font-medium">{new Date(request.created_at).toLocaleString("uz-UZ")}</div>
          </div>
        </div>
        <div className="text-slate-400 text-sm mb-1">Tavsif</div>
        <p className="whitespace-pre-wrap text-slate-800">{request.description}</p>
        {request.completion_note && (
          <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
            <div className="mb-1 font-medium">Bajarilgan ish izohi</div>
            {request.completion_note}
          </div>
        )}
      </div>

      {isAdmin && (
        <form onSubmit={handleAssign} className="mb-6 rounded-xl border border-slate-200 bg-white p-5">
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
        </form>
      )}

      {isStaffAssignee && request.status !== "completed" && request.status !== "cancelled" && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-3 font-medium text-slate-800">Harakatlar</div>
          <div className="flex flex-wrap gap-2">
            {request.status === "assigned" && (
              <button
                onClick={() => handleStatus("in_progress")}
                disabled={busy}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
              >
                ▶️ Ishga boshladim
              </button>
            )}
          </div>
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
        </div>
      )}

      {isRequester && request.status === "completed" && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5">
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

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-3 font-medium text-slate-800">Yozishmalar</div>
        <div className="mb-4 space-y-2">
          {messages.length === 0 && <div className="text-sm text-slate-400">Hozircha xabarlar yo'q</div>}
          {messages.map((m) => (
            <div key={m.id} className={`rounded-lg p-3 text-sm ${m.visibility === "internal" ? "bg-slate-100" : "bg-brand-50"}`}>
              <div className="mb-1 text-xs text-slate-400">
                {m.visibility === "internal" ? "Ichki" : "Murojaatchiga"} · {new Date(m.created_at).toLocaleString("uz-UZ")}
              </div>
              {m.body}
            </div>
          ))}
        </div>
        {(isStaffAssignee || isAdmin) && (
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input
              value={messageBody}
              onChange={(e) => setMessageBody(e.target.value)}
              placeholder="Xabar yozing..."
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Yuborish
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
