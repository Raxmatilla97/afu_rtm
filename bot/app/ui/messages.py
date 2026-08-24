"""Rendering one thread message as text.

A message can now be text, a file, or both, and a thread listing has to stay readable in
all three cases — a bare gap where a voice note was would read as a bug.
"""

from afu_shared.media import kind_label
from afu_shared.models import RequestMessage


def format_message_body(message: RequestMessage) -> str:
    """The body of one message, with any attached file named in place."""
    parts: list[str] = []
    if message.body:
        parts.append(message.body)
    for attachment in message.attachments:
        label = kind_label(attachment.kind)
        if attachment.duration_seconds:
            label = f"{label} ({_duration(attachment.duration_seconds)})"
        parts.append(f"<i>{label}</i>")
    return "\n".join(parts) if parts else "<i>— bo'sh xabar —</i>"


def _duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"
