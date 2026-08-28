import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { requestsApi } from "@/api/requests";
import { describeError } from "@/api/errors";
import { employeesApi } from "@/api/reference";
import { AttachmentGrid } from "@/components/AttachmentView";
import { DeadlineBanner } from "@/components/DeadlineBanner";
import { RequestChat } from "@/components/RequestChat";
import { RequesterCard } from "@/components/RequesterCard";
import { RichText } from "@/components/RichTextEditor";
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

/**
 * The four reasons a request actually comes back, as finished wordings.
 *
 * Presets rather than a dropdown of codes: whatever is picked here is sent to the reporter
 * verbatim over Telegram, so it has to read as a sentence written to a person. Each one is
 * a starting point — the text stays editable, and the label is only what the button says.
 */
const RETURN_PRESETS: { label: string; text: string }[] = [
  {
    label: "Noto'g'ri manzil",
    text:
      "Murojaat noto'g'ri manzilga yuborilgan — bu masala RTM vakolatiga kirmaydi. " +
      "Iltimos, tegishli bo'limga murojaat qiling.",
  },
  {
    label: "Ma'lumot yetarli emas",
    text:
      "Murojaatda ma'lumot yetarli emas. Iltimos, muammo qaysi bino va xonada, qaysi " +
      "qurilmada ekanini yozing, xatolik matni yoki surati bo'lsa qo'shib, qaytadan yuboring.",
  },
  {
    label: "Takroriy murojaat",
    text:
      "Bu muammo bo'yicha allaqachon murojaat mavjud. Takroriy murojaat yopildi — " +
      "javobni oldingi murojaatingizda kuzatib boring.",
  },
  {
    label: "Muammo hal bo'lgan",
    text:
      "Muammo hal qilingan yoki o'z-o'zidan bartaraf bo'lgan, qo'shimcha ish talab " +
      "qilinmaydi. Agar takrorlansa, yangi murojaat yuboring.",
  },
];

export function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const requestId = Number(id);
  const { session, isAdmin } = useAuth();
  const navigate = useNavigate();

  const [request, setRequest] = useState<RequestItem | null>(null);
  const [attachments, setAttachments] = useState<RequestAttachmentItem[]>([]);
  const [staffList, setStaffList] = useState<Employee[]>([]);
  const [assigneeIds, setAssigneeIds] = useState<number[]>([]);
  const [deadline, setDeadline] = useState("");
  const [completionNote, setCompletionNote] = useState("");
  const [ratingScore, setRatingScore] = useState(0);
  const [returning, setReturning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Separate from `error`, which reports a failed action on a request that did load.
  const [loadError, setLoadError] = useState<string | null>(null);

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
    setLoadError(null);
    // Reachable by anyone who types a URL: a staffer who is not on this job, or an
    // employee who did not report it, is refused here. Without this catch the promise
    // rejected into nothing and the page sat on "Yuklanmoqda..." for ever.
    load().catch((e) => setLoadError(describeError(e)));
  }, [requestId]);

  useEffect(() => {
    // rtmStaff, not the admin-only directory: a Boshliq may assign work but may not read
    // the whole employee list, so the old call answered 403 and left this form with no
    // names in it — a button that looked broken rather than forbidden.
    if (canManage) employeesApi.rtmStaff().then(setStaffList).catch(() => setStaffList([]));
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

  async function handleReturn(reason: string) {
    await run(async () => {
      await requestsApi.returnToRequester(requestId, reason);
      setReturning(false);
      await load();
    });
  }

  /**
   * Erase the request entirely. Admin only — see the endpoint for why it exists.
   *
   * A typed confirmation rather than a plain OK/Cancel: this is the one action on the page
   * with nothing behind it, and the request number is right there on screen to copy, so
   * typing it is a second of work that makes "wrong tab" impossible.
   */
  async function handleDelete() {
    const typed = window.prompt(
      `${request?.display_number} butunlay o'chiriladi — yozishmalar, fayllar va guruhdagi ` +
        "kartochka bilan birga. Buni ortga qaytarib bo'lmaydi.\n\n" +
        `Tasdiqlash uchun murojaat raqamini yozing: ${request?.display_number}`,
    );
    if (typed === null) return;
    if (typed.trim().toUpperCase() !== request?.display_number.toUpperCase()) {
      setError("Murojaat raqami mos kelmadi — hech narsa o'chirilmadi.");
      return;
    }
    await run(async () => {
      await requestsApi.remove(requestId);
      navigate("/requests", { replace: true });
    });
  }

  async function handleRate(score: number) {
    await run(async () => {
      await requestsApi.rate(requestId, score);
      setRatingScore(score);
    });
  }

  if (!request) {
    if (!loadError) return <div className="text-slate-400">Yuklanmoqda...</div>;
    return (
      <div className="mx-auto max-w-xl">
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {loadError}
        </div>
        <Link
          to="/requests"
          className="mt-4 inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm text-slate-700 hover:bg-slate-50"
        >
          ← Murojaatlar ro'yxati
        </Link>
      </div>
    );
  }

  // Files posted inside the conversation are already rendered in their own bubble; the
  // gallery is for what came with the request itself, so it does not repeat them.
  const requestFiles = attachments.filter((a) => a.message_id === null);

  const isReturned = request.status === "returned";
  // Returning a finished job would tell the reporter their solved problem was rejected,
  // and returning an already-returned one would send the notification twice.
  const canReturn = canManage && !isReturned && request.status !== "completed";

  return (
    // Full width, like the list this page opens from. The layout below is already two
    // columns with a capped chat rail, so the extra room goes to the description, the
    // attachment grid and the assign form rather than to empty margins.
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">{request.display_number}</h1>
          <div className="text-sm text-slate-500">
            {request.category_label} · {request.source === "bot" ? "Telegram" : "Veb"}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={request.status} />
          {canReturn && (
            <button
              onClick={() => setReturning(true)}
              disabled={busy}
              className="min-h-11 rounded-lg bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              🚫 Qaytarib yuborish
            </button>
          )}
          {isAdmin && (
            <button
              onClick={handleDelete}
              disabled={busy}
              title="Murojaatni butunlay o'chirish"
              className="min-h-11 rounded-lg border border-red-300 px-4 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              🗑 O'chirish
            </button>
          )}
        </div>
      </div>

      {isReturned && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <div className="font-semibold">🚫 Bu murojaat qaytarib yuborilgan</div>
          <p className="mt-1 whitespace-pre-wrap">{request.return_reason || "—"}</p>
          <div className="mt-1 text-xs text-red-500">{dt(request.returned_at)}</div>
        </div>
      )}

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
            <RichText
              html={request.description_html}
              text={request.description}
              className="text-slate-800"
            />
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

          {canManage && !isReturned && (
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

          {isStaffAssignee && !isReturned && request.status !== "completed" && request.status !== "cancelled" && (
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

      {returning && canReturn && (
        <ReturnModal
          displayNumber={request.display_number}
          busy={busy}
          error={error}
          onClose={() => setReturning(false)}
          onSubmit={handleReturn}
        />
      )}
    </div>
  );
}

/**
 * Why a request is being sent back, written to the person who filed it.
 *
 * Deliberately a dialog with a text box rather than a confirm(): this text is delivered to
 * the reporter's Telegram word for word and is the only thing they will be told, so it has
 * to be written on purpose. A preset fills the box and leaves it editable — the common case
 * is one of the four with a detail added.
 *
 * `error` is rendered in here rather than only on the page behind: a refusal shown under a
 * modal is a refusal nobody reads, and the dialog stays open on failure so the wording that
 * was just typed is not lost.
 */
function ReturnModal({
  displayNumber,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  displayNumber: string;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-800">Murojaatni qaytarib yuborish</h2>
            <p className="truncate text-xs text-slate-500">
              {displayNumber} — murojaatchiga sabab bilan qaytariladi
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✖
          </button>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!reason.trim()) return;
            onSubmit(reason.trim());
          }}
          className="flex-1 overflow-y-auto p-5"
        >
          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="mb-2 text-xs font-medium text-slate-600">Tayyor javoblar</div>
          <div className="mb-4 flex flex-wrap gap-2">
            {RETURN_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setReason(preset.text)}
                className="min-h-9 rounded-full border border-slate-300 px-3 text-xs text-slate-700 hover:bg-slate-50"
              >
                {preset.label}
              </button>
            ))}
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">
              Sabab (murojaatchiga shu matn boradi)
            </span>
            <textarea
              required
              rows={5}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nega qaytarilmoqda? Murojaatchi nima qilishi kerak?"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>

          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Qaytarilgan murojaat ro'yxatdan chiqadi va uni faqat «Qaytarib yuborilgan»
            filtri orqali ko'rish mumkin. Murojaatchiga va uni olgan xodimga Telegram orqali
            xabar yuboriladi.
          </p>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50"
            >
              Bekor qilish
            </button>
            <button
              type="submit"
              disabled={busy || !reason.trim()}
              className="min-h-11 rounded-lg bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {busy ? "Yuborilmoqda..." : "🚫 Qaytarib yuborish"}
            </button>
          </div>
        </form>
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
