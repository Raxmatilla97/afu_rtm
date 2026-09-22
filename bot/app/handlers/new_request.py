"""New-request flow.

Ordinary employees file a request: category, description, optional files, published. A
Boshliq files a **directive** and passes through two more screens first — a deadline and a
team — so that what reaches the RTM group already says how long the job has and whose it
is. See ``app.screens.new_request`` for the screens and ``Employee.can_file_managed_request``
for who gets them.
"""

from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.assignments import set_assignees
from afu_shared.enums import AttachmentKind, RequestSource, RequestStatus
from afu_shared.media import describe_attachments, extract_media, persist_media
from afu_shared.models import (
    Category,
    Employee,
    Request,
    RequestAttachment,
    RequestStatusHistory,
)
from afu_shared.people import role_label, role_of, short_name
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
        # Stamped once, at creation. The group card reads this for the rest of the
        # request's life instead of re-deriving it from the requester's current flags.
        requester_role=role_of(employee),
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

    if employee.can_file_managed_request:
        # Not announced yet: the card a directive produces carries a deadline and a team,
        # and posting one now would put an "unclaimed" card in the group that is edited
        # thirty seconds later. The group would be told twice about one job.
        await _start_directive(state, bot, redis, callback.message.chat.id, employee, request, "")
        return

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
    employee: Employee,
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

    if employee.can_file_managed_request:
        await _start_directive(
            state, bot, redis, callback.message.chat.id, employee, request, summary
        )
        return

    await state.clear()
    # Announced only now, not when the request row was created: the card carries the
    # attachments, and posting it mid-upload would show the group an empty one.
    await _announce(session, arq_pool, request)

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_submitted_screen(request.display_number, summary, request.id),
    )


# --------------------------------------------------------------------------------------
# The Boshliq's directive: deadline, then team, then one published card.
# --------------------------------------------------------------------------------------


async def _start_directive(
    state: FSMContext,
    bot: Bot,
    redis: Redis,
    chat_id: int,
    employee: Employee,
    request: Request,
    summary: str,
) -> None:
    """Hand a finished draft over to the deadline step instead of publishing it."""
    role = role_label(role_of(employee)) or "BOSHLIQ"
    await state.update_data(request_id=request.id, role=role, assignee_ids=[])
    await state.set_state(NewRequestStates.awaiting_deadline)
    await render(
        bot, redis, chat_id,
        screens.build_deadline_screen(request.display_number, role, summary),
    )


async def _staff_page(session: AsyncSession) -> list[Employee]:
    """Everyone who can be given a job. Blocked and departed staff are not offered."""
    return list(
        (
            await session.execute(
                select(Employee)
                .where(
                    Employee.is_rtm_staff.is_(True),
                    Employee.is_blocked.is_(False),
                    Employee.access_revoked.is_(False),
                    Employee.is_active.is_(True),
                )
                .order_by(Employee.full_name)
            )
        ).scalars()
    )


async def _render_assignees(
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    chat_id: int,
    request: Request,
    page: int,
) -> None:
    data = await state.get_data()
    staff = await _staff_page(session)
    pages = max(1, (len(staff) + screens.STAFF_PAGE_SIZE - 1) // screens.STAFF_PAGE_SIZE)
    page = min(max(1, page), pages)
    start = (page - 1) * screens.STAFF_PAGE_SIZE

    await render(
        bot, redis, chat_id,
        screens.build_assignees_screen(
            request.display_number,
            data.get("role", "BOSHLIQ"),
            request.deadline_at,
            staff[start : start + screens.STAFF_PAGE_SIZE],
            list(data.get("assignee_ids", [])),
            page,
            pages,
        ),
    )


@router.callback_query(NewRequestStates.awaiting_deadline, FlowCB.filter(F.act == "dl"))
async def choose_deadline(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await state.clear()
        return

    # 0 minutes means "no deadline", which is a real choice: plenty of directives are about
    # who does the job rather than about when.
    request.deadline_at = (
        datetime.now(timezone.utc) + timedelta(minutes=callback_data.n)
        if callback_data.n > 0
        else None
    )
    await session.flush()

    await state.set_state(NewRequestStates.awaiting_assignees)
    await _render_assignees(state, session, bot, redis, callback.message.chat.id, request, 1)


@router.callback_query(NewRequestStates.awaiting_assignees, FlowCB.filter(F.act == "page"))
async def page_assignees(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await state.clear()
        return
    await _render_assignees(
        state, session, bot, redis, callback.message.chat.id, request, callback_data.page
    )


@router.callback_query(NewRequestStates.awaiting_assignees, FlowCB.filter(F.act == "pick"))
async def toggle_assignee(
    callback: CallbackQuery,
    callback_data: FlowCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    """Add or remove one name. Order is kept — the first pick is the mas'ul."""
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await callback.answer()
        await state.clear()
        return

    target = await session.get(Employee, callback_data.eid)
    if target is None or not target.is_rtm_staff or not target.is_eligible:
        await callback.answer("Bu xodimni tayinlab bo'lmaydi.", show_alert=True)
        return

    chosen = list(data.get("assignee_ids", []))
    if target.id in chosen:
        chosen.remove(target.id)
        await callback.answer(f"❌ {short_name(target.full_name)} olib tashlandi")
    else:
        # Appended, never prepended: choosing a second person must not quietly demote the
        # first out of the mas'ul seat.
        chosen.append(target.id)
        prefix = "⭐ Mas'ul: " if len(chosen) == 1 else "✅ "
        await callback.answer(prefix + short_name(target.full_name))

    await state.update_data(assignee_ids=chosen)
    await _render_assignees(
        state, session, bot, redis, callback.message.chat.id, request, callback_data.page
    )


@router.callback_query(NewRequestStates.awaiting_assignees, FlowCB.filter(F.act == "send"))
async def send_directive(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    """Assign, publish, and brief everyone who was named."""
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    request = await session.get(Request, data.get("request_id", 0))
    if request is None:
        await state.clear()
        return

    # Re-checked at the moment it takes effect, not only when the flow began: a role can be
    # withdrawn while somebody is still choosing names.
    if not employee.can_file_managed_request:
        await state.clear()
        await _announce(session, arq_pool, request)
        await render(
            bot, redis, callback.message.chat.id,
            screens.build_submitted_screen(request.display_number, "", request.id),
        )
        return

    chosen = list(data.get("assignee_ids", []))
    names: list[str] = []
    if chosen:
        # set_assignees owns the assignee table, the primary column, the status and the
        # history row — before the card is published, so the group's first sight of this
        # job already says whose it is.
        await set_assignees(session, request, chosen)
        await session.flush()
        for employee_id in chosen:
            person = await session.get(Employee, employee_id)
            if person is not None:
                names.append(short_name(person.full_name))

    deadline_at = request.deadline_at
    role = data.get("role", "BOSHLIQ")
    display_number = request.display_number
    request_id = request.id

    await state.clear()
    await _announce(session, arq_pool, request)
    # Overrides the "request.create" _announce just marked. One row per update, and the
    # more specific one is worth keeping — but only when something was actually directed:
    # a Boshliq who skipped both steps has filed an ordinary request.
    if chosen or deadline_at:
        mark("request.directive", target=display_number)
    for employee_id in chosen:
        await arq_pool.enqueue_job("notify_request_assigned", request_id, employee_id)

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_directive_sent_screen(display_number, role, deadline_at, names, request_id),
    )
