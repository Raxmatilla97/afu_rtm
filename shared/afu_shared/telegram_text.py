"""Escaping text that came from a person before it goes into a Telegram message.

Every message this platform sends uses ``parse_mode="HTML"``, and almost every one of them
interpolates something a user typed: a fault description, a completion note, a name that
arrived from HEMIS. Telegram then parses the result as markup.

Two things go wrong without this module, and both have been reachable from the "new
request" form:

* **The message stops being deliverable.** A description containing ``<`` or a bare ``&``
  makes Telegram answer "can't parse entities" and refuse the whole send. The group card is
  never posted, the assignee is never briefed, and nothing in the interface says why —
  the request simply sits there looking ignored.
* **The message becomes somebody else's.** ``<a href="http://…">To'lov qiling</a>`` typed
  into a description renders as a real link inside the official RTM group card, wearing the
  card's authority. That is a phishing vector handed to anyone who can file a request.

So: any value that a person can influence is passed through ``esc`` at the point it is
interpolated. Our own wording and tags stay as they are — that is the whole distinction
this module exists to keep visible.
"""

import html

__all__ = ["esc"]


def esc(value: object, *, default: str = "") -> str:
    """HTML-escape one value for a Telegram message.

    ``None`` becomes ``default`` (usually an em dash or an empty string) rather than the
    string "None", which is what the callers used to print when a field was empty.

    ``quote=False``: Telegram's HTML subset only breaks on ``<``, ``>`` and ``&``, and
    escaping apostrophes as well would put ``&#x27;`` in the middle of every Uzbek word.
    """
    if value is None:
        return default
    return html.escape(str(value), quote=False)
