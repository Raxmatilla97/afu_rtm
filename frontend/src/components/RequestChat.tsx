import { useCallback, useEffect, useRef, useState } from "react";
import { requestsApi } from "@/api/requests";
import { AttachmentView } from "@/components/AttachmentView";
import type { RequestMessageItem } from "@/types";

interface Props {
  requestId: number;
  /** Decides which side a bubble sits on — see `isFromRequester`. */
  requesterEmployeeId: number;
  requesterName: string;
  /** Employee id of the viewer, or null for an admin. */
  myEmployeeId: number | null;
  /** Internal notes are an RTM-only concept, so only staff and admins may write one. */
  canWriteInternal: boolean;
  /**
   * False for admins. An attachment records the employee who uploaded it, and an admin
   * account has no employee row — so the server refuses. Better to not offer the button
   * than to hand back a 403 after the file has uploaded.
   */
  canAttach: boolean;
  /** Called after this component sends something, so the page can refresh the rest. */
  onSent: () => Promise<void> | void;
}

/** How often to pull new messages while the tab is in front. */
const POLL_MS = 5000;

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" });
}

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (sameDay(date, today)) return "Bugun";
  if (sameDay(date, yesterday)) return "Kecha";
  return date.toLocaleDateString("uz-UZ", { day: "2-digit", month: "long", year: "numeric" });
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/**
 * The conversation on a request, as a chat.
 *
 * Sides are decided by *role*, not by who is looking: the reporter is always on the left
 * and RTM is always on the right. Two people reading the same thread therefore see the
 * same picture, which is what makes it possible to talk about ("the photo on the left")
 * — the usual "me on the right" rule would give every viewer a different layout.
 */
export function RequestChat({
  requestId,
  requesterEmployeeId,
  requesterName,
  myEmployeeId,
  canWriteInternal,
  canAttach,
  onSent,
}: Props) {
  const [messages, setMessages] = useState<RequestMessageItem[]>([]);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  // Tracked in a ref rather than state: the poll callback reads it, and putting it in
  // state would rebuild the interval on every incoming message.
  const lastIdRef = useRef<number>(0);

  const refresh = useCallback(async () => {
    const incoming = await requestsApi.messages(requestId);
    const newestId = incoming.length ? incoming[incoming.length - 1].id : 0;
    // Only re-render when something actually arrived. Replacing the array every five
    // seconds would restart video playback and fight the user's scrolling.
    if (newestId !== lastIdRef.current || incoming.length !== messages.length) {
      lastIdRef.current = newestId;
      setMessages(incoming);
    }
  }, [requestId, messages.length]);

  useEffect(() => {
    lastIdRef.current = 0;
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]);

  useEffect(() => {
    // Polling rather than a socket: this is a helpdesk thread, not a trading floor, and a
    // five-second delay costs nothing next to the operational weight of keeping WebSocket
    // connections alive through the reverse proxy.
    const tick = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const timer = window.setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [refresh]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    // Only follow the conversation when the reader is already at the bottom; yanking them
    // down mid-scroll while they read something older is worse than missing one message.
    const nearBottom =
      scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 160;
    if (nearBottom) endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    if (!body.trim() && files.length === 0) return;

    setBusy(true);
    setError(null);
    try {
      // Files first: the server links them to the message it is about to create, and only
      // then notifies Telegram — so the notification never goes out ahead of its evidence.
      const uploaded = [];
      for (const file of files) {
        uploaded.push(await requestsApi.uploadAttachment(requestId, file));
      }
      await requestsApi.postMessage(
        requestId,
        body,
        internal ? "internal" : "to_requester",
        uploaded.map((a) => a.id),
      );
      setBody("");
      setFiles([]);
      await refresh();
      await onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuborib bo'lmadi");
    } finally {
      setBusy(false);
    }
  }

  const panel = (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-800">Yozishmalar</div>
          <div className="text-xs text-slate-500">
            {messages.length} xabar · jonli yangilanadi
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? "Kichraytirish (Esc)" : "Butun ekranda ochish"}
          className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm text-slate-600 hover:bg-white"
        >
          {expanded ? "🗕" : "🗖"}
        </button>
      </header>

      <div ref={scrollerRef} className="flex-1 space-y-1 overflow-y-auto bg-slate-50/60 px-4 py-4">
        {messages.length === 0 && (
          <div className="py-10 text-center text-sm text-slate-400">
            Hozircha xabarlar yo'q — birinchi bo'lib yozing
          </div>
        )}
        {messages.map((m, index) => {
          const previous = index > 0 ? messages[index - 1] : null;
          const newDay =
            !previous ||
            new Date(previous.created_at).toDateString() !==
              new Date(m.created_at).toDateString();
          // Role decides the side, not the viewer: reporter left, RTM right, always.
          const fromRequester = m.author_employee_id === requesterEmployeeId;
          const isInternal = m.visibility === "internal";
          const mine = myEmployeeId !== null && m.author_employee_id === myEmployeeId;
          const author = m.author_name || (fromRequester ? requesterName : "RTM");

          return (
            <div key={m.id}>
              {newDay && (
                <div className="my-3 flex justify-center">
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-500 shadow-sm">
                    {dayLabel(m.created_at)}
                  </span>
                </div>
              )}
              <div className={`flex gap-2 py-1 ${fromRequester ? "justify-start" : "justify-end"}`}>
                {fromRequester && <Avatar name={author} tone="requester" />}
                <div className={`max-w-[78%] min-w-0 ${fromRequester ? "" : "text-right"}`}>
                  <div
                    className={`inline-block w-full rounded-2xl px-3.5 py-2 text-left text-sm shadow-sm ${
                      isInternal
                        ? "rounded-tr-sm border border-dashed border-amber-300 bg-amber-50 text-amber-900"
                        : fromRequester
                          ? "rounded-tl-sm bg-white text-slate-800"
                          : "rounded-tr-sm bg-brand-600 text-white"
                    }`}
                  >
                    <div
                      className={`mb-0.5 text-xs font-medium ${
                        isInternal
                          ? "text-amber-700"
                          : fromRequester
                            ? "text-slate-500"
                            : "text-brand-100"
                      }`}
                    >
                      {isInternal && "🗂 Ichki · "}
                      {author}
                      {mine && " (siz)"}
                    </div>
                    {m.body && <div className="whitespace-pre-wrap break-words">{m.body}</div>}
                    {m.attachments.length > 0 && (
                      <div className="mt-2 space-y-2">
                        {m.attachments.map((a) => (
                          <AttachmentView key={a.id} attachment={a} />
                        ))}
                      </div>
                    )}
                    <div
                      className={`mt-1 text-right text-[11px] ${
                        isInternal
                          ? "text-amber-600"
                          : fromRequester
                            ? "text-slate-400"
                            : "text-brand-100"
                      }`}
                    >
                      {timeLabel(m.created_at)}
                    </div>
                  </div>
                </div>
                {!fromRequester && <Avatar name={author} tone={isInternal ? "internal" : "rtm"} />}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} className="border-t border-slate-200 bg-white p-3">
        {files.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {files.map((file, index) => (
              <span
                key={`${file.name}-${index}`}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700"
              >
                📎 {file.name}
                <button
                  type="button"
                  onClick={() => setFiles(files.filter((_, i) => i !== index))}
                  className="text-slate-400 hover:text-red-600"
                  aria-label="Faylni olib tashlash"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {error && <div className="mb-2 text-xs text-red-600">{error}</div>}

        <div className="flex items-end gap-2">
          {canAttach && (
            <label className="cursor-pointer rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50">
              📎
              <input
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  setFiles([...files, ...Array.from(e.target.files ?? [])]);
                  // Reset so picking the same file twice in a row still fires onChange.
                  e.target.value = "";
                }}
              />
            </label>
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={1}
            placeholder="Xabar yozing... (Enter — yuborish, Shift+Enter — yangi qator)"
            className="max-h-40 flex-1 resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy || (!body.trim() && files.length === 0)}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "..." : "Yuborish"}
          </button>
        </div>

        {canWriteInternal && (
          <label className="mt-2 flex items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={internal}
              onChange={(e) => setInternal(e.target.checked)}
            />
            Ichki izoh (murojaatchi ko'rmaydi)
          </label>
        )}
      </form>
    </div>
  );

  if (!expanded) return panel;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-900/60 p-3 sm:p-6">
      <div className="mx-auto flex h-full w-full max-w-4xl flex-col">{panel}</div>
    </div>
  );
}

function Avatar({ name, tone }: { name: string; tone: "requester" | "rtm" | "internal" }) {
  const palette = {
    requester: "bg-slate-200 text-slate-700",
    rtm: "bg-brand-100 text-brand-700",
    internal: "bg-amber-100 text-amber-800",
  }[tone];
  return (
    <div
      title={name}
      className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${palette}`}
    >
      {initials(name)}
    </div>
  );
}
