/**
 * The browser half of `afu_shared/richtext.py` — same allowlist, same normalisation.
 *
 * Both halves exist on purpose. This one runs while somebody is typing, so what they paste
 * out of Word is cleaned before it ever reaches the editor and the preview is honest about
 * what will be stored. The server one runs on what actually arrives, which is the only copy
 * that matters: a request written by hand never executes a line of this file.
 *
 * The parsing is done by the browser's own HTML parser through `DOMParser`, and the result
 * is rebuilt element by element rather than filtered in place — an attribute that is not
 * copied across cannot survive, whatever it was called.
 */

const ALLOWED_TAGS = new Set([
  "P",
  "BR",
  "STRONG",
  "EM",
  "U",
  "S",
  "UL",
  "OL",
  "LI",
  "BLOCKQUOTE",
  "PRE",
  "CODE",
  "H2",
  "H3",
  "A",
]);

/** Browsers disagree about which tag `execCommand` emits; these are the same thing. */
const TAG_ALIASES: Record<string, string> = {
  DIV: "P",
  B: "STRONG",
  I: "EM",
  STRIKE: "S",
  DEL: "S",
  H1: "H2",
  H4: "H3",
  H5: "H3",
  H6: "H3",
};

/** Dropped with their contents. Everything else unknown keeps its text and loses its tag. */
const DROP_ENTIRELY = new Set(["SCRIPT", "STYLE", "TEMPLATE", "IFRAME", "OBJECT", "EMBED"]);

const ALLOWED_SCHEMES = ["http:", "https:", "mailto:", "tel:"];

/** Blocks that become a line break in the plain reading. */
const BLOCK_TAGS = new Set(["P", "UL", "OL", "BLOCKQUOTE", "PRE", "H2", "H3"]);

export function safeHref(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  try {
    // A bare domain is what people paste; anything else without a scheme is refused rather
    // than guessed at, so `javascript:` can never be reached by omission.
    const url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `https://${value}`);
    return ALLOWED_SCHEMES.includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function rebuild(source: Node, target: Node, doc: Document): void {
  source.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) {
      target.appendChild(doc.createTextNode(child.textContent ?? ""));
      return;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) return;

    const element = child as Element;
    const name = TAG_ALIASES[element.tagName] ?? element.tagName;

    if (DROP_ENTIRELY.has(element.tagName)) return;

    if (!ALLOWED_TAGS.has(name)) {
      // An unknown wrapper loses its tag, never its text: a pasted <span> around a
      // sentence must not delete the sentence.
      rebuild(element, target, doc);
      return;
    }

    if (name === "BR") {
      target.appendChild(doc.createElement("br"));
      return;
    }

    if (name === "A") {
      const href = safeHref(element.getAttribute("href") ?? "");
      if (!href) {
        rebuild(element, target, doc);
        return;
      }
      const anchor = doc.createElement("a");
      anchor.setAttribute("href", href);
      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer nofollow");
      rebuild(element, anchor, doc);
      target.appendChild(anchor);
      return;
    }

    const clean = doc.createElement(name.toLowerCase());
    rebuild(element, clean, doc);
    target.appendChild(clean);
  });
}

/** `html` reduced to the allowlist. Returns "" when nothing readable survives. */
export function sanitizeHtml(html: string): string {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const out = doc.createElement("div");
  rebuild(doc.body, out, doc);
  const result = out.innerHTML.trim();
  // An "empty" contenteditable is a paragraph holding one non-breaking space, and it would
  // otherwise pass every emptiness check in the app.
  return htmlToText(result) ? result : "";
}

/**
 * The plain reading of `html` — what Telegram gets, and what the character count counts.
 *
 * Matches `html_to_text` in the Python module closely enough that the length shown while
 * typing is the length that ends up on the bot card.
 */
export function htmlToText(html: string): string {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");

  const walk = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
    if (node.nodeType !== Node.ELEMENT_NODE) return "";

    const element = node as Element;
    const inner = Array.from(element.childNodes).map(walk).join("");
    if (element.tagName === "BR") return "\n";
    if (element.tagName === "LI") return `\n• ${inner}`;
    if (BLOCK_TAGS.has(element.tagName)) return `\n${inner}\n`;
    return inner;
  };

  return walk(doc.body)
    .replace(/\u00a0/g, " ")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function isEmptyHtml(html: string): boolean {
  return htmlToText(html).length === 0;
}
