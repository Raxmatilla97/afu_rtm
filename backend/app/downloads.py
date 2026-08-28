"""How an uploaded file is allowed to come back out of the server.

The content type stored with an attachment is whatever the uploader's browser claimed, and
the request attachment endpoint serves files **inline** so a photo of a broken socket
displays in place. Those two facts together were a stored cross-site scripting hole: upload
``report.html`` with ``Content-Type: text/html``, send the link to a colleague, and the
page runs on ``rtm.afu.uz`` — same origin as the session, the admin panel and everything
else.

So the type is decided here, not by the uploader. Media renders inline because that is the
whole point of attaching it; anything else is handed over as a download with a type the
browser will not execute, and ``nosniff`` stops it guessing otherwise.
"""

__all__ = ["INLINE_SAFE_PREFIXES", "NOSNIFF", "serve_headers"]

#: Types a browser renders without running anything the uploader wrote.
INLINE_SAFE_PREFIXES = ("image/", "video/", "audio/")
#: PDF joins them: receipts and invoices are the second most common attachment here, and
#: browser PDF viewers are sandboxed.
INLINE_SAFE_EXACT = frozenset({"application/pdf"})
#: SVG is the exception inside ``image/`` and the reason this list exists at all: it is an
#: XML document that runs script when a browser displays it, so an "image" upload would
#: otherwise be the same cross-site scripting hole by a different route.
INLINE_UNSAFE_EXACT = frozenset({"image/svg+xml", "image/svg"})

NOSNIFF = {"X-Content-Type-Options": "nosniff"}


def _is_inline_safe(content_type: str) -> bool:
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered in INLINE_UNSAFE_EXACT:
        return False
    return lowered.startswith(INLINE_SAFE_PREFIXES) or lowered in INLINE_SAFE_EXACT


def serve_headers(
    content_type: str | None, filename: str, *, want_download: bool
) -> tuple[str, dict[str, str]]:
    """Decide the media type and headers for one stored file.

    Returns ``(media_type, headers)``. Anything that is not obviously safe to render comes
    back as ``application/octet-stream`` with an ``attachment`` disposition, whatever the
    uploader said it was — including when the caller asked for inline.
    """
    declared = (content_type or "").strip()
    inline = not want_download and bool(declared) and _is_inline_safe(declared)

    media_type = declared if inline else "application/octet-stream"
    disposition = "inline" if inline else "attachment"

    headers = {
        "Content-Disposition": f'{disposition}; filename="{ascii_filename(filename)}"',
        **NOSNIFF,
    }
    return media_type, headers


def ascii_filename(name: str) -> str:
    """Content-Disposition is a latin-1 header; a Cyrillic filename would break it.

    Quotes are stripped as well: an unescaped one inside the quoted string lets a filename
    inject its own header parameters.
    """
    return name.encode("ascii", "replace").decode("ascii").replace('"', "_").replace("\\", "_")
