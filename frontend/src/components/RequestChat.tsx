import { useEffect, useRef, useState } from "react";
import { requestsApi } from "@/api/requests";
import { AttachmentView } from "@/components/AttachmentView";
import type { RequestMessageItem } from "@/types";

interface Props {
  requestId: number;
  messages: RequestMessageItem[];
  /** Employee id of the viewer, or null for an admin — decides which side a bubble sits on. */
  myEmployeeId: number | null;
  /** Internal notes are an RTM-only concept, so only staff and admins may write one. */
  canWriteInternal: boolean;
  /**
   * False for admins. An attachment records the employee who uploaded it, and an admin
   * account has no employee row — so the server refuses. Better to not offer the button
   * than to hand back a 403 after the file has uploaded.
   */
  canAttach: boolean;
  onSent: () => Promise<void> | void;
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The conversation on a request, as a chat.
 *
 * A chat rather than a list of records because that is what it is in Telegram, and the two
 * interfaces show the same thread: someone answering on the web and someone answering on
 * their phone should recognise the same conversation.
 */
export function RequestChat({
  requestId,
  messages,
  myEmployeeId,
  canWriteInternal,
  canAttach,
  onSent,
}: Props) {
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
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
      await onSent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuborib bo'lmadi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3 text-sm font-medium text-slate-800">
        Yozishmalar
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="py-8 text-center text-sm text-slate-400">Hozircha xabarlar yo'q</div>
        )}
        {messages.map((m) => {
          const mine = myEmployeeId !== null && m.author_employee_id === myEmployeeId;
          const isInternal = m.visibility === "internal";
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                  isInternal
                    ? "border border-dashed border-amber-300 bg-amber-50 text-amber-900"
                    : mine
                      ? "bg-brand-600 text-white"
                      : "bg-slate-100 text-slate-800"
                }`}
              >
                <div
                  className={`mb-1 text-xs ${
                    isInternal ? "text-amber-700" : mine ? "text-brand-100" : "text-slate-500"
                  }`}
                >
                  {isInternal && "🗂 Ichki · "}
                  {m.author_name || "RTM"} · {timeLabel(m.created_at)}
                </div>
                {m.body && <div className="whitespace-pre-wrap">{m.body}</div>}
                {m.attachments.length > 0 && (
                  <div className="mt-2 space-y-2">
                    {m.attachments.map((a) => (
                      <AttachmentView key={a.id} attachment={a} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} className="border-t border-slate-200 p-3">
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
                void send(e as unknown as React.FormEvent);
              }
            }}
            rows={1}
            placeholder="Xabar yozing..."
            className="max-h-32 flex-1 resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
}
