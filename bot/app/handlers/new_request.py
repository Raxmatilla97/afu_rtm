"""New-request flow."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import AttachmentKind, RequestSource, RequestStatus
from afu_shared.media import describe_attachments, extract_media, persist_media
from afu_shared.models import (
    Category,
    Employee,
    Request,
    RequestAttachment,
    RequestStatusHistory,
)
from app.callbacks import CatCB, FlowCB
from app.filters.media import HAS_MEDIA
from app.middlewares.activity import mark
from app.screens import new_request as screens
from app.states.new_request import NewRequestStates
from app.ui.anchor import render
from app.utils.transient import send_transient

router = Router(name="new_request")

#: Stand-in description when the whole request arrives as a voice note or video and the
#: sender added no caption. Something has to go in ``description`` — it is what every list
#: screen and notification shows — and naming the medium is more use than an empty line.
_MEDIA_ONLY_DESCRIPTION = {
    AttachmentKind.VOICE: "🎤 Ovozli murojaat",
    AttachmentKind.VIDEO_NOTE: "⭕️ Video xabar orqali murojaat",
    AttachmentKind.VIDEO: "🎬 Video murojaat",
    AttachmentKind.AUDIO: "🎵 Audio murojaat",
    AttachmentKind.PHOTO: "🖼 Rasm bilan murojaat",
    AttachmentKind.DOCUMENT: "📄 Fayl bilan murojaat",
}


@router.callback_query(NewRequestStates.awaiting_category, CatCB.filter())
async def choose_category(
    callback: CallbackQuery,
    callback_data: CatCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    category = await session.get(Category, callback_data.slug)
    if category is None:
        await callback.answer("Kategoriya topilmadi.", show_alert=True)
        return

    await state.update_data(category_slug=category.slug, category_label=category.label_uz)
    await state.set_state(NewRequestStates.awaiting_description)
    await render(
        bot, redis, callback.message.chat.id, screens.build_description_screen(category.label_uz)
    )


@router.message(NewRequestStates.awaiting_description, F.text)
async def enter_description(
    message: Message, state: FSMContext, bot: Bot, redis: Redis
) -> None:
    description = (message.text or "").strip()
    data = await state.get_data()

    await state.update_data(description=description)
    await state.set_state(NewRequestStates.awaiting_attachment_choice)
    await render(
        bot, redis, message.chat.id,
        screens.build_attachment_choice_screen(data.get("category_label", "—"), description),
    )


@router.message(NewRequestStates.awaiting_description, HAS_MEDIA)
async def describe_with_media(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    """The request itself arrived as a voice note, a video, or a photo.

    Not everyone can comfortably type out a fault on a phone, so the medium the user
    reached for first is accepted as the submission. The request is created immediately and
    the flow continues straight into the attachment step — the file is already the first
    attachment, so asking "do you want to attach something?" would be nonsense here.
    """
    payload = extract_media(message)
    if payload is None:
        return

    data = await state.get_data()
    description = payload.caption or _MEDIA_ONLY_DESCRIPTION.get(payload.kind, "Murojaat")
    request = await _create_request(session, employee, {**data, "description": description})

    await persist_media(
        session, bot, message, request_id=request.id, employee_id=employee.id
    )

    await state.update_data(request_id=request.id, description=description)
    await state.set_state(NewRequestStates.awaiting_media)
    await _render_media_screen(session, bot, redis, message.chat.id, request)


async def _create_request(
    session: AsyncSession, employee: Employee, data: dict
) -> Request:
    request = Request(
        requester_employee_id=employee.id,
        category_slug=data["category_slug"],
        description=data["description"],
        status=RequestStatus.NEW.value,
        source=RequestSource.BOT.value,
    )
    session.add(request)
    await session.flush()

    session.add(
        RequestStatusHistory(
            request_id=request.id,
            from_status=None,
            to_status=RequestStatus.NEW.value,
            changed_by_employee_id=employee.id,
        )
    )
    await session.flush()
    return request


async def _attachments_of(session: AsyncSession, request_id: int) -> list[RequestAttachment]:
    return list(
        (
            await session.execute(
                select(RequestAttachment)
                .where(RequestAttachment.request_id == request_id)
                .order_by(RequestAttachment.id)
            )
        ).scalars()
    )


async def _announce(session: AsyncSession, arq_pool: ArqRedis, request: Request) -> None:
    """Publish the request to the RTM groups, once it is finished being written.

    Committing first is not optional: the worker builds the card from its own read of the
    database, and a job that overtakes this transaction would render a request that is not
    there yet.
    """
    await session.commit()
    mark("request.create", target=request.display_number)
    await arq_pool.enqueue_job("publish_request_card", request.id)


async def _render_media_screen(
    session: AsyncSession, bot: Bot, redis: Redis, chat_id: int, request: Request
) -> None:
    summary = describe_attachments(await _attachments_of(session, request.id))
    await render(
        bot, redis, chat_id,
        screens.build_media_screen(request.display_number, summary),
        # Re-anchor so the prompt and its "Tayyor" button sit directly under the file the
        # user just sent, instead of staying put while the uploads scroll past it.
        force_new=True,
    )


@router.callback_query(NewRequestStates.awaiting_attachment_choice, FlowCB.filter(F.act == "attach_no"))
async def attach_no(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _create_request(session, employee, await state.get_data())
    await state.clear()
    await _announce(session, arq_pool, request)
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_submitted_screen(request.display_number, "", request.id),
    )


@router.callback_query(NewRequestStates.awaiting_attachment_choice, FlowCB.filter(F.act == "attach_yes"))
async def attach_yes(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    request = await _create_request(session, employee, await state.get_data())
    await state.update_data(request_id=request.id)
    await state.set_state(NewRequestStates.awaiting_media)
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_media_screen(request.display_number, ""),
    )


@router.message(NewRequestStates.awaiting_media, HAS_MEDIA)
async def receive_media(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        # The draft is gone (restart, or a state left over from a deleted request); dropping
        # out is better than crashing on a file the user just spent time recording.
        await state.clear()
        return

    attachment = await persist_media(
        session, bot, message, request_id=request.id, employee_id=employee.id
    )
    if attachment is None:
        return

    await _render_media_screen(session, bot, redis, message.chat.id, request)


@router.message(NewRequestStates.awaiting_media, F.text)
async def media_step_got_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    """Typed text during the upload step extends the description rather than being lost."""
    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await state.clear()
        return

    extra = (message.text or "").strip()
    if extra:
        request.description = f"{request.description}\n{extra}"
        await session.flush()
        await send_transient(
            bot, redis, arq_pool, message.chat.id, "📝 Izoh tavsifga qo'shildi."
        )
    await _render_media_screen(session, bot, redis, message.chat.id, request)


@router.callback_query(NewRequestStates.awaiting_media, FlowCB.filter(F.act == "media_done"))
async def finish_media(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await state.clear()
        return
    summary = describe_attachments(await _attachments_of(session, request.id))
    await state.clear()
    # Announced only now, not when the request row was created: the card carries the
    # attachments, and posting it mid-upload would show the group an empty one.
    await _announce(session, arq_pool, request)

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_submitted_screen(request.display_number, summary, request.id),
    )
