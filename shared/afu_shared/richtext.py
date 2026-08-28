"""Rich request descriptions: an allowlist sanitizer and an HTML-to-text reducer.

The web form lets people write a formatted description — bold, lists, headings, a link.
Telegram cannot show that. The bot cards, the assignment briefings and the overdue warnings
all pass ``request.description`` through ``esc()``, so storing markup in that column would
put literal ``<p>`` tags in front of every RTM staffer.

So a request carries both: ``description_html`` is what the web renders, ``description``
stays the plain reading of the same text and is what every Telegram surface keeps using.
``html_to_text`` below is the only thing that derives the second from the first, so the two
can never drift into saying different things.

The sanitizer is a re-serializer, not a filter: the input is parsed and a fresh document is
written from the tags that survive the allowlist. Anything unrecognised — a script, an
event handler, a ``javascript:`` href, an unclosed tag — never reaches the output, because
the output is only ever built from what this module chose to write. The browser sanitizes
too, and that copy is the one that cannot be trusted: the payload arrives over HTTP and a
hand-written POST never runs our JavaScript at all.
"""

import re
from html import escape, unescape
from html.parser import HTMLParser

#: Tags kept as themselves. Everything here is inert — no source, no script, no styling
#: hooks — which is why the set is spelled out rather than derived from "not dangerous".
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "u",
        "s",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "h2",
        "h3",
        "a",
    }
)

#: Tags rewritten to an equivalent that is on the list. ``contenteditable`` emits ``div``
#: for a paragraph and the legacy presentational tags for bold and italic, and browsers
#: disagree about which — normalising here means the stored markup reads the same whichever
#: browser typed it.
TAG_ALIASES: dict[str, str] = {
    "div": "p",
    "b": "strong",
    "i": "em",
    "strike": "s",
    "del": "s",
    "h1": "h2",
    "h4": "h3",
    "h5": "h3",
    "h6": "h3",
}

#: No closing tag, and nothing nests inside them.
VOID_TAGS: frozenset[str] = frozenset({"br"})

#: Dropped along with everything they contain. For every other unknown tag the text is kept
#: and only the tag disappears — a stray ``<span>`` around a sentence must not delete the
#: sentence.
DROP_WITH_CONTENT: frozenset[str] = frozenset({"script", "style", "template", "head", "title"})

#: Schemes a link may use. Everything else — ``javascript:`` above all, but ``data:`` too —
#: is refused and the link degrades to plain text.
ALLOWED_SCHEMES: tuple[str, ...] = ("http://", "https://", "mailto:", "tel:")

#: Ceiling on the stored markup. Long enough for a page of prose with formatting, short
#: enough that nobody can park a megabyte of nested tags in a text column.
MAX_HTML_LENGTH = 60_000

#: Where a newline belongs in the plain reading. ``li`` is handled separately — it gets a
#: bullet rather than a break.
_BLOCK_TAGS: tuple[str, ...] = ("p", "ul", "ol", "blockquote", "pre", "h2", "h3")

#: Placeholder for an anchor whose href was refused. Never reaches storage — it exists only
#: so the matching end tag has something to close and the link text survives as prose.
_NOOP_OPEN = "\x00a\x00"
_NOOP_CLOSE = "\x00/a\x00"


def safe_href(value: str | None) -> str | None:
    """``value`` as a link we are willing to publish, or None."""
    if not value:
        return None
    href = unescape(value).strip()
    # Control characters are how ``java\tscript:`` gets past a naive prefix check.
    href = "".join(ch for ch in href if ch.isprintable())
    if not href:
        return None
    lowered = href.lower()
    if lowered.startswith(ALLOWED_SCHEMES):
        return href
    # A bare domain is what people actually paste. Anything else carrying a scheme-looking
    # prefix is refused rather than guessed at.
    if "://" in lowered or ":" in lowered.split("/")[0]:
        return None
    return f"https://{href}"


class _Sanitizer(HTMLParser):
    """Rebuilds the document from the tags that survive the allowlist."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        #: Elements we actually emitted, so end tags can be matched and leftovers closed.
        #: Each entry is (tag, emitted_markup_or_noop).
        self._open: list[tuple[str, bool]] = []
        #: Depth inside a dropped subtree; text is thrown away while this is non-zero.
        self._suppress = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._suppress += 1
            return
        if self._suppress:
            return

        tag = TAG_ALIASES.get(tag, tag)
        if tag not in ALLOWED_TAGS:
            # Unknown wrapper: its text still belongs to the document.
            return

        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}>")
            return

        if tag == "a":
            href = safe_href(dict(attrs).get("href"))
            if href is None:
                self.parts.append(_NOOP_OPEN)
                self._open.append(("a", True))
                return
            self.parts.append(
                f'<a href="{escape(href, quote=True)}" target="_blank" '
                'rel="noopener noreferrer nofollow">'
            )
            self._open.append(("a", False))
            return

        self.parts.append(f"<{tag}>")
        self._open.append((tag, False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = TAG_ALIASES.get(tag.lower(), tag.lower())
        if not self._suppress and tag in VOID_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self._suppress = max(0, self._suppress - 1)
            return
        if self._suppress:
            return

        tag = TAG_ALIASES.get(tag, tag)
        if tag in VOID_TAGS or not any(name == tag for name, _ in self._open):
            return

        # Close everything opened inside it as well: malformed nesting must not leave an
        # element hanging open across the rest of the document.
        while self._open:
            name, noop = self._open.pop()
            self.parts.append(_NOOP_CLOSE if noop else f"</{name}>")
            if name == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._suppress:
            return
        self.parts.append(escape(data, quote=False))

    def close(self) -> None:
        super().close()
        while self._open:
            name, noop = self._open.pop()
            self.parts.append(_NOOP_CLOSE if noop else f"</{name}>")


def sanitize_html(raw: str | None) -> str:
    """``raw`` reduced to the allowlist, or "" when nothing readable survives.

    Safe to call on text that is not HTML at all: plain text comes back escaped and intact.
    """
    if not raw:
        return ""

    parser = _Sanitizer()
    parser.feed(raw[:MAX_HTML_LENGTH])
    parser.close()
    html = "".join(parser.parts).replace(_NOOP_OPEN, "").replace(_NOOP_CLOSE, "")
    # An "empty" document out of a contenteditable is a paragraph holding one non-breaking
    # space, and it would otherwise pass every emptiness check in the system.
    if not html_to_text(html):
        return ""
    return html.strip()


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str | None) -> str:
    """The plain reading of ``html`` — what Telegram, the bot and every list show.

    List items keep their bullet and blocks keep their line breaks: the result is read by a
    person in a chat window, not parsed by anything.
    """
    if not html:
        return ""

    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    # The bullet replaces the opening tag and the closing one is simply dropped: a newline
    # at both ends would put a blank line between every item in the list.
    text = re.sub(r"(?i)<li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)</li\s*>", "", text)
    for tag in _BLOCK_TAGS:
        text = re.sub(rf"(?i)</?{tag}[^>]*>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    text = text.replace(" ", " ")
    # Trailing spaces go first, so a line of nothing but whitespace collapses together with
    # the blank lines around it rather than propping them apart.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
