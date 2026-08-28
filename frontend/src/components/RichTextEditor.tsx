import { useCallback, useEffect, useRef, useState } from "react";
import { htmlToText, safeHref, sanitizeHtml } from "@/lib/richtext";

/**
 * A formatting toolbar over a `contenteditable`, with no library behind it.
 *
 * Every rich-text package worth using is a dependency measured in hundreds of kilobytes,
 * and this application ships React, the router and nothing else — the whole frontend has
 * three runtime dependencies. What a request description actually needs is bold, a list,
 * a heading and the occasional link, all of which `document.execCommand` has done in every
 * browser for twenty years. It is deprecated and not going anywhere.
 *
 * Two rules make it behave:
 *
 * * The toolbar buttons cancel `mousedown`. A button that takes focus destroys the
 *   selection before the command can run, which is why a naive toolbar appears to do
 *   nothing at all.
 * * The node's HTML is written from `value` only when the change came from outside.
 *   Feeding our own output back on every keystroke would put the caret at position zero
 *   after every letter typed.
 */

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  /** Minimum height of the writing area, in Tailwind classes. */
  minHeightClass?: string;
  disabled?: boolean;
}

type Command = { key: string; label: string; title: string; run: () => void; state?: string };

function exec(command: string, argument?: string): void {
  document.execCommand(command, false, argument);
}

export function RichTextEditor({
  value,
  onChange,
  placeholder = "Yozing...",
  minHeightClass = "min-h-[12rem]",
  disabled = false,
}: Props) {
  const editorRef = useRef<HTMLDivElement>(null);
  const savedRange = useRef<Range | null>(null);
  const [active, setActive] = useState<Record<string, boolean>>({});
  const [linkDraft, setLinkDraft] = useState<string | null>(null);
  const [linkError, setLinkError] = useState(false);

  const emit = useCallback(() => {
    const node = editorRef.current;
    if (node) onChange(sanitizeHtml(node.innerHTML));
  }, [onChange]);

  useEffect(() => {
    const node = editorRef.current;
    if (!node) return;
    // Only when the value did not come from this editor. `document.activeElement` is the
    // cheapest reliable test for that: while somebody is typing, the node is focused.
    if (document.activeElement !== node && node.innerHTML !== value) {
      node.innerHTML = value;
    }
  }, [value]);

  useEffect(() => {
    // Firefox and Chrome disagree on what Enter inserts. Asking for <p> makes the stored
    // markup the same shape in both, which is what keeps the server's normalisation from
    // being the only thing holding them together.
    try {
      document.execCommand("defaultParagraphSeparator", false, "p");
    } catch {
      // Not supported: the server maps <div> to <p> anyway.
    }
  }, []);

  const refreshState = useCallback(() => {
    const node = editorRef.current;
    if (!node || !node.contains(document.getSelection()?.anchorNode ?? null)) return;
    const read = (name: string) => {
      try {
        return document.queryCommandState(name);
      } catch {
        return false;
      }
    };
    setActive({
      bold: read("bold"),
      italic: read("italic"),
      underline: read("underline"),
      strikeThrough: read("strikeThrough"),
      insertUnorderedList: read("insertUnorderedList"),
      insertOrderedList: read("insertOrderedList"),
    });
  }, []);

  useEffect(() => {
    document.addEventListener("selectionchange", refreshState);
    return () => document.removeEventListener("selectionchange", refreshState);
  }, [refreshState]);

  function apply(run: () => void) {
    editorRef.current?.focus();
    run();
    refreshState();
    emit();
  }

  /**
   * Pasting goes through the same allowlist as saving.
   *
   * Without this, a paste out of Word arrives as a wall of `<span style="mso-...">` and
   * the server quietly strips it on save — so what the writer sees while typing is not
   * what anyone else will ever read.
   */
  function handlePaste(event: React.ClipboardEvent<HTMLDivElement>) {
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain");
    // The allowlist can empty a paste completely — copying a table or an image out of a
    // web page leaves nothing this editor keeps. Falling through to the plain text means
    // the paste still does something, rather than appearing to be ignored.
    const cleaned = sanitizeHtml(event.clipboardData.getData("text/html"));
    if (cleaned) {
      exec("insertHTML", cleaned);
    } else if (text) {
      exec("insertText", text);
    }
    emit();
  }

  function openLink() {
    const selection = document.getSelection();
    // The range is captured before the input steals focus, and restored when it is
    // applied: without it the link lands wherever the caret happened to be left.
    savedRange.current = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
    setLinkError(false);
    setLinkDraft("");
  }

  function applyLink(raw: string) {
    const href = safeHref(raw);
    if (!href) {
      setLinkError(true);
      return;
    }
    const node = editorRef.current;
    node?.focus();
    const selection = document.getSelection();
    if (savedRange.current && selection) {
      selection.removeAllRanges();
      selection.addRange(savedRange.current);
    }
    if (selection?.isCollapsed) {
      // Nothing was selected, so there is no text to turn into a link — insert the address
      // as its own visible text rather than creating an invisible empty anchor.
      //
      // Escaped even though safeHref has already vetted the scheme: the URL parser leaves
      // a double quote alone inside an opaque path such as mailto:, and this string is
      // being written into an attribute.
      const escaped = href.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
      exec("insertHTML", `<a href="${escaped}">${escaped}</a>`);
    } else {
      exec("createLink", href);
    }
    setLinkDraft(null);
    emit();
  }

  const commands: Command[] = [
    { key: "bold", label: "B", title: "Qalin (Ctrl+B)", run: () => exec("bold"), state: "bold" },
    {
      key: "italic",
      label: "I",
      title: "Kursiv (Ctrl+I)",
      run: () => exec("italic"),
      state: "italic",
    },
    {
      key: "underline",
      label: "U",
      title: "Tagi chizilgan (Ctrl+U)",
      run: () => exec("underline"),
      state: "underline",
    },
    {
      key: "strike",
      label: "S",
      title: "Chizib tashlangan",
      run: () => exec("strikeThrough"),
      state: "strikeThrough",
    },
    { key: "h2", label: "H1", title: "Sarlavha", run: () => exec("formatBlock", "<h2>") },
    { key: "h3", label: "H2", title: "Kichik sarlavha", run: () => exec("formatBlock", "<h3>") },
    {
      key: "ul",
      label: "•",
      title: "Belgili ro'yxat",
      run: () => exec("insertUnorderedList"),
      state: "insertUnorderedList",
    },
    {
      key: "ol",
      label: "1.",
      title: "Raqamli ro'yxat",
      run: () => exec("insertOrderedList"),
      state: "insertOrderedList",
    },
    { key: "quote", label: "❝", title: "Iqtibos", run: () => exec("formatBlock", "<blockquote>") },
    { key: "p", label: "¶", title: "Oddiy matn", run: () => exec("formatBlock", "<p>") },
    {
      key: "clear",
      label: "✖",
      title: "Formatni tozalash",
      run: () => {
        exec("removeFormat");
        exec("formatBlock", "<p>");
      },
    },
  ];

  const plainLength = htmlToText(value).length;

  return (
    <div
      className={`rounded-lg border bg-white ${
        disabled ? "border-slate-200 opacity-60" : "border-slate-300 focus-within:border-brand-500"
      }`}
    >
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200 px-2 py-1.5">
        {commands.map((command) => (
          <button
            key={command.key}
            type="button"
            title={command.title}
            aria-label={command.title}
            disabled={disabled}
            // Keeps the selection alive: focus moving to the button would collapse it, and
            // the command would then apply to nothing.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => apply(command.run)}
            className={`min-h-8 min-w-8 rounded px-2 text-sm transition-colors disabled:opacity-40 ${
              command.state && active[command.state]
                ? "bg-brand-600 text-white"
                : "text-slate-600 hover:bg-slate-100"
            } ${command.key === "bold" ? "font-bold" : ""} ${
              command.key === "italic" ? "italic" : ""
            } ${command.key === "underline" ? "underline" : ""} ${
              command.key === "strike" ? "line-through" : ""
            }`}
          >
            {command.label}
          </button>
        ))}
        <span className="mx-1 h-5 w-px bg-slate-200" />
        <button
          type="button"
          title="Havola qo'shish"
          aria-label="Havola qo'shish"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={openLink}
          className="min-h-8 rounded px-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-40"
        >
          🔗
        </button>
      </div>

      {linkDraft !== null && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-2 py-2">
          <input
            autoFocus
            value={linkDraft}
            onChange={(e) => {
              setLinkDraft(e.target.value);
              setLinkError(false);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyLink(linkDraft);
              }
              if (e.key === "Escape") setLinkDraft(null);
            }}
            placeholder="rtm.afu.uz yoki https://..."
            className={`min-h-9 flex-1 rounded-lg border px-3 text-sm ${
              linkError ? "border-red-400" : "border-slate-300"
            }`}
          />
          <button
            type="button"
            onClick={() => applyLink(linkDraft)}
            className="min-h-9 rounded-lg bg-brand-600 px-3 text-sm font-medium text-white hover:bg-brand-700"
          >
            Qo'shish
          </button>
          <button
            type="button"
            onClick={() => setLinkDraft(null)}
            className="min-h-9 rounded-lg border border-slate-300 px-3 text-sm text-slate-600 hover:bg-white"
          >
            Bekor
          </button>
          {linkError && (
            <span className="w-full text-xs text-red-600">
              Havola manzili noto'g'ri. Faqat http, https, mailto va tel qabul qilinadi.
            </span>
          )}
        </div>
      )}

      <div
        ref={editorRef}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label="Tavsif"
        data-placeholder={placeholder}
        onInput={emit}
        onBlur={emit}
        onPaste={handlePaste}
        onKeyUp={refreshState}
        onMouseUp={refreshState}
        className={`rich-text rich-editor ${minHeightClass} w-full overflow-y-auto px-3 py-2 text-sm text-slate-800 outline-none`}
      />

      <div className="flex justify-between border-t border-slate-100 px-3 py-1.5 text-xs text-slate-400">
        <span>Matnni belgilab, yuqoridagi tugmalar bilan bezang.</span>
        <span className="tabular-nums">{plainLength} belgi</span>
      </div>
    </div>
  );
}

/**
 * Renders a stored description.
 *
 * `dangerouslySetInnerHTML` with a second sanitize pass in front of it. The markup came
 * from our own database and was already cleaned on the way in, but this is the one place
 * where a mistake anywhere upstream turns into script execution in an administrator's
 * browser — so it is cleaned again here, where it costs nothing.
 *
 * `text` is the fallback for everything filed through the bot, which has no markup at all.
 */
export function RichText({
  html,
  text,
  className = "",
}: {
  html?: string | null;
  text: string;
  className?: string;
}) {
  if (!html) {
    return <p className={`whitespace-pre-wrap ${className}`}>{text}</p>;
  }
  return (
    <div
      className={`rich-text ${className}`}
      dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
    />
  );
}
