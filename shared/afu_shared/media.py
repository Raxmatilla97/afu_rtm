"""Telegram media: reading it off an incoming message, storing it, and re-sending it.

Lives in ``shared`` rather than in the bot because both sides of every conversation need
it. The bot captures what a requester sends; the worker replays it into the assigned
staffer's chat. If those two grew separate copies they would drift, and the symptom would
be silent — a voice message arriving as an unplayable file attachment.

The design rule throughout: **relay by ``file_id``, never by re-upload.** Telegram will
re-send a file it already holds for free and, crucially, as the same *kind* of media, so a
round video stays a round video. Our own downloaded copy exists for the web interface, and
as a fallback for the rare file that has no usable handle.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import AttachmentKind
from afu_shared.models import RequestAttachment
from afu_shared.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Longest flood-wait we are willing to sit out inline. Beyond this the job gives up rather
#: than holding a worker slot for minutes.
MAX_FLOOD_WAIT_SECONDS = 30


async def _tolerating_flood(call: Callable[[], Awaitable[T]]) -> T:
    """Run a Bot API call, waiting out one flood limit if Telegram asks.

    Replaying a set of files is several calls in a row, which is exactly the shape Telegram
    throttles. Letting the error escape would fail the whole arq job, and the retry would
    re-send everything that had already arrived.
    """
    try:
        return await call()
    except TelegramRetryAfter as exc:
        if exc.retry_after > MAX_FLOOD_WAIT_SECONDS:
            raise
        logger.info("Flood limit: waiting %ss before retrying", exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        return await call()


#: The Bot API refuses ``getFile`` above this, so a larger file can only ever be relayed by
#: handle. We do not even try, to keep a predictable error out of the logs.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

#: Telegram caps an album at 10 items.
MEDIA_GROUP_LIMIT = 10

KIND_LABELS: dict[str, str] = {
    AttachmentKind.PHOTO.value: "🖼 Rasm",
    AttachmentKind.VIDEO.value: "🎬 Video",
    AttachmentKind.VOICE.value: "🎤 Ovozli xabar",
    AttachmentKind.VIDEO_NOTE.value: "⭕️ Video xabar",
    AttachmentKind.AUDIO.value: "🎵 Audio",
    AttachmentKind.DOCUMENT.value: "📄 Fayl",
}

#: Kinds that can share one album. Voice, audio and round videos cannot be grouped with
#: anything, and a video note cannot be grouped at all.
_GROUPABLE = (AttachmentKind.PHOTO.value, AttachmentKind.VIDEO.value)


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, KIND_LABELS[AttachmentKind.DOCUMENT.value])


def describe_attachments(attachments: list[RequestAttachment]) -> str:
    """One-line summary like "2 × 🖼 Rasm, 1 × 🎤 Ovozli xabar"."""
    if not attachments:
        return ""
    counts: dict[str, int] = {}
    for att in attachments:
        counts[att.kind] = counts.get(att.kind, 0) + 1
    return ", ".join(f"{n} × {kind_label(kind)}" for kind, n in counts.items())


@dataclass(frozen=True)
class MediaPayload:
    """Everything an incoming Telegram message tells us about the file it carries."""

    kind: AttachmentKind
    file_id: str
    file_unique_id: str
    file_size: int | None = None
    duration_seconds: int | None = None
    original_filename: str | None = None
    content_type: str | None = None
    extension: str = "bin"
    #: Text the sender typed alongside the file, if any.
    caption: str | None = None


def extract_media(message: Message) -> MediaPayload | None:
    """Read the single file off an incoming message, or None if it carries none.

    Order matters: a Telegram message has at most one media field, but ``document`` is the
    catch-all and must be checked last so a video sent as a file is still recognised by its
    more specific field when Telegram populates one.
    """
    caption = (message.caption or "").strip() or None

    if message.photo:
        # Sizes come smallest-first; the last is the original the sender chose.
        photo = message.photo[-1]
        return MediaPayload(
            kind=AttachmentKind.PHOTO,
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            file_size=photo.file_size,
            content_type="image/jpeg",
            extension="jpg",
            caption=caption,
        )

    if message.voice:
        v = message.voice
        return MediaPayload(
            kind=AttachmentKind.VOICE,
            file_id=v.file_id,
            file_unique_id=v.file_unique_id,
            file_size=v.file_size,
            duration_seconds=v.duration,
            content_type=v.mime_type or "audio/ogg",
            extension="ogg",
            caption=caption,
        )

    if message.video_note:
        vn = message.video_note
        return MediaPayload(
            kind=AttachmentKind.VIDEO_NOTE,
            file_id=vn.file_id,
            file_unique_id=vn.file_unique_id,
            file_size=vn.file_size,
            duration_seconds=vn.duration,
            content_type="video/mp4",
            extension="mp4",
            caption=caption,
        )

    if message.video:
        vid = message.video
        return MediaPayload(
            kind=AttachmentKind.VIDEO,
            file_id=vid.file_id,
            file_unique_id=vid.file_unique_id,
            file_size=vid.file_size,
            duration_seconds=vid.duration,
            original_filename=vid.file_name,
            content_type=vid.mime_type or "video/mp4",
            extension=_extension_of(vid.file_name, "mp4"),
            caption=caption,
        )

    if message.audio:
        aud = message.audio
        return MediaPayload(
            kind=AttachmentKind.AUDIO,
            file_id=aud.file_id,
            file_unique_id=aud.file_unique_id,
            file_size=aud.file_size,
            duration_seconds=aud.duration,
            original_filename=aud.file_name,
            content_type=aud.mime_type or "audio/mpeg",
            extension=_extension_of(aud.file_name, "mp3"),
            caption=caption,
        )

    if message.document:
        doc = message.document
        return MediaPayload(
            kind=AttachmentKind.DOCUMENT,
            file_id=doc.file_id,
            file_unique_id=doc.file_unique_id,
            file_size=doc.file_size,
            original_filename=doc.file_name,
            content_type=doc.mime_type,
            extension=_extension_of(doc.file_name, "bin"),
            caption=caption,
        )

    return None


def _extension_of(filename: str | None, fallback: str) -> str:
    if not filename or "." not in filename:
        return fallback
    ext = filename.rsplit(".", 1)[-1].lower()
    # Guard against a "filename" that is really a long dotted string.
    return ext if ext.isalnum() and len(ext) <= 8 else fallback


def relative_dir(request_id: int) -> str:
    return f"requests/{request_id}"


async def download_to_storage(bot: Bot, payload: MediaPayload, request_id: int) -> str | None:
    """Save a copy under ``storage_root``; return its relative path, or None.

    A None here is not an error the user should ever see: the attachment still works
    everywhere Telegram is involved, and only the web preview is unavailable.
    """
    if payload.file_size and payload.file_size > MAX_DOWNLOAD_BYTES:
        logger.info(
            "Skipping local copy of %s (%s bytes): above the Bot API download limit",
            payload.kind.value, payload.file_size,
        )
        return None

    filename = f"{uuid.uuid4().hex}.{payload.extension}"
    target_dir = Path(settings.storage_root) / relative_dir(request_id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file = await bot.get_file(payload.file_id)
        if not file.file_path:
            return None
        await bot.download_file(file.file_path, destination=target_dir / filename)
    except (TelegramBadRequest, TelegramNetworkError, OSError) as exc:
        logger.warning("Could not store a local copy of %s: %s", payload.kind.value, exc)
        return None

    return f"{relative_dir(request_id)}/{filename}"


async def persist_media(
    session: AsyncSession,
    bot: Bot,
    message: Message,
    *,
    request_id: int,
    employee_id: int,
    message_row_id: int | None = None,
) -> RequestAttachment | None:
    """Store the message's file as an attachment row. Returns None if there was none."""
    payload = extract_media(message)
    if payload is None:
        return None

    file_path = await download_to_storage(bot, payload, request_id)
    attachment = RequestAttachment(
        request_id=request_id,
        message_id=message_row_id,
        uploaded_by_employee_id=employee_id,
        kind=payload.kind.value,
        file_path=file_path,
        original_filename=payload.original_filename,
        content_type=payload.content_type,
        file_size=payload.file_size,
        duration_seconds=payload.duration_seconds,
        telegram_file_id=payload.file_id,
        telegram_file_unique_id=payload.file_unique_id,
    )
    session.add(attachment)
    await session.flush()
    return attachment


def _source(attachment: RequestAttachment) -> str | FSInputFile | None:
    """Prefer Telegram's handle; fall back to our copy on disk."""
    if attachment.telegram_file_id:
        return attachment.telegram_file_id
    if attachment.file_path:
        path = Path(settings.storage_root) / attachment.file_path
        if path.exists():
            return FSInputFile(path, filename=attachment.original_filename or path.name)
    return None


async def send_attachment(
    bot: Bot,
    chat_id: int,
    attachment: RequestAttachment,
    *,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int | None:
    """Re-send one attachment as its original kind.

    Returns the id of the message it became, or None if it could not be sent. Callers keep
    those ids so a chat can be tidied up afterwards — a set of replayed files is worth
    seeing once, not worth leaving above every screen that follows.
    """
    source = _source(attachment)
    if source is None:
        return None

    method = {
        AttachmentKind.PHOTO.value: bot.send_photo,
        AttachmentKind.VIDEO.value: bot.send_video,
        AttachmentKind.VOICE.value: bot.send_voice,
        AttachmentKind.AUDIO.value: bot.send_audio,
        AttachmentKind.VIDEO_NOTE.value: bot.send_video_note,
    }.get(attachment.kind, bot.send_document)

    kwargs: dict = {"reply_markup": reply_markup}
    if attachment.kind != AttachmentKind.VIDEO_NOTE.value:
        # A round video has no caption field at all; anything meant to go with it has to be
        # sent as its own message first by the caller.
        kwargs |= {"caption": caption, "parse_mode": "HTML"}

    try:
        sent = await _tolerating_flood(partial(method, chat_id, source, **kwargs))
    except TelegramForbiddenError:
        logger.info("Cannot send attachment %s to %s: bot blocked", attachment.id, chat_id)
        return None
    except (TelegramBadRequest, TelegramRetryAfter) as exc:
        logger.warning("Failed to send attachment %s to %s: %s", attachment.id, chat_id, exc)
        return None
    return sent.message_id


def _input_media(attachment: RequestAttachment, caption: str | None):
    source = _source(attachment)
    if source is None:
        return None
    if attachment.kind == AttachmentKind.PHOTO.value:
        return InputMediaPhoto(media=source, caption=caption, parse_mode="HTML")
    if attachment.kind == AttachmentKind.VIDEO.value:
        return InputMediaVideo(media=source, caption=caption, parse_mode="HTML")
    if attachment.kind == AttachmentKind.AUDIO.value:
        return InputMediaAudio(media=source, caption=caption, parse_mode="HTML")
    return InputMediaDocument(media=source, caption=caption, parse_mode="HTML")


async def send_attachments(
    bot: Bot,
    chat_id: int,
    attachments: list[RequestAttachment],
    *,
    caption: str | None = None,
) -> list[int]:
    """Deliver a whole set of attachments in a readable order.

    Photos and videos travel as one album so the recipient sees them as a single block
    instead of a wall of separate messages; voice notes, round videos and files follow
    individually because Telegram will not group them. ``caption`` rides on the first item
    of the album, or on the first standalone file when there is no album.

    Returns the ids of every message sent, so the caller can clear them away later.
    """
    if not attachments:
        return []

    groupable = [a for a in attachments if a.kind in _GROUPABLE]
    singles = [a for a in attachments if a.kind not in _GROUPABLE]
    sent: list[int] = []
    pending_caption = caption

    for start in range(0, len(groupable), MEDIA_GROUP_LIMIT):
        chunk = groupable[start : start + MEDIA_GROUP_LIMIT]
        media = [
            item
            for item in (
                _input_media(att, pending_caption if index == 0 else None)
                for index, att in enumerate(chunk)
            )
            if item is not None
        ]
        if not media:
            continue
        if len(media) == 1:
            # A one-item album is rejected by Telegram; send it as a normal message.
            single = await send_attachment(bot, chat_id, chunk[0], caption=pending_caption)
            if single is not None:
                sent.append(single)
        else:
            try:
                messages = await _tolerating_flood(
                    partial(bot.send_media_group, chat_id, media=media)
                )
                sent.extend(m.message_id for m in messages)
            except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc:
                logger.warning("Media group to %s failed, falling back: %s", chat_id, exc)
                for att in chunk:
                    one = await send_attachment(bot, chat_id, att)
                    if one is not None:
                        sent.append(one)
        pending_caption = None

    for att in singles:
        if att.kind == AttachmentKind.VIDEO_NOTE.value and pending_caption:
            # A round video carries no caption of its own.
            try:
                note = await _tolerating_flood(
                    partial(bot.send_message, chat_id, pending_caption, parse_mode="HTML")
                )
                sent.append(note.message_id)
            except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
                pass
            pending_caption = None
        one = await send_attachment(bot, chat_id, att, caption=pending_caption)
        if one is not None:
            sent.append(one)
            pending_caption = None

    return sent
