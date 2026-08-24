import type { RequestAttachmentItem } from "@/types";

function humanSize(bytes: number | null): string {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function humanDuration(seconds: number | null): string {
  if (!seconds) return "";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * One attachment, played or shown in place.
 *
 * Playing in place is the whole point: a voice reply that has to be downloaded before it
 * can be heard is strictly worse than the same reply in Telegram, and the web interface
 * would stop being a real alternative to the bot.
 */
export function AttachmentView({ attachment }: { attachment: RequestAttachmentItem }) {
  const { url, kind, original_filename, content_type } = attachment;

  if (!url) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 px-3 py-2 text-xs text-slate-500">
        {attachment.kind_label} — faqat Telegramda mavjud (hajmi katta)
      </div>
    );
  }

  if (kind === "photo") {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="block">
        <img
          src={url}
          alt={original_filename || "Rasm"}
          loading="lazy"
          // max-w-full matters inside a chat bubble: without it a wide photo pushes the
          // bubble past the column and the whole thread scrolls sideways.
          className="max-h-72 w-auto max-w-full rounded-lg border border-slate-200 object-cover"
        />
      </a>
    );
  }

  if (kind === "video" || kind === "video_note") {
    return (
      <video
        src={url}
        controls
        preload="metadata"
        // A round video is round in Telegram; keeping the shape here is what makes it
        // recognisable as the same message rather than an unexplained square clip.
        className={
          kind === "video_note"
            ? "h-48 w-48 rounded-full border border-slate-200 object-cover"
            : "max-h-72 w-full rounded-lg border border-slate-200"
        }
      />
    );
  }

  if (kind === "voice" || kind === "audio") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-2">
        <div className="mb-1 text-xs text-slate-500">
          {attachment.kind_label}
          {attachment.duration_seconds ? ` · ${humanDuration(attachment.duration_seconds)}` : ""}
        </div>
        <audio src={url} controls preload="metadata" className="w-full" />
      </div>
    );
  }

  return (
    <a
      href={`${url}?download=1`}
      className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
    >
      <span className="text-lg">📄</span>
      <span className="min-w-0">
        <span className="block truncate font-medium">{original_filename || "Fayl"}</span>
        <span className="text-xs text-slate-400">
          {[content_type, humanSize(attachment.file_size)].filter(Boolean).join(" · ")}
        </span>
      </span>
    </a>
  );
}

/** A set of attachments laid out as a gallery. */
export function AttachmentGrid({ attachments }: { attachments: RequestAttachmentItem[] }) {
  if (attachments.length === 0) return null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {attachments.map((a) => (
        <AttachmentView key={a.id} attachment={a} />
      ))}
    </div>
  );
}
