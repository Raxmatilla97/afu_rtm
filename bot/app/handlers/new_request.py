"""New-request flow."""

import uuid
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestSource, RequestStatus
from afu_shared.models import Category, Employee, Request, RequestAttachment, RequestStatusHistory
from afu_shared.settings import settings
from app.callbacks import CatCB, FlowCB
from app.screens import menu, new_request as screens
from app.states.new_request import NewRequestStates
from app.ui.anchor import render
from app.utils.transient import send_transient

router = Router(name="new_request")


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


@router.callback_query(NewRequestStates.awaiting_attachment_choice, FlowCB.filter(F.act == "attach_no"))
async def attach_no(
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
    await state.clear()
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_submitted_screen(request.display_number, 0, request.id),
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
    await state.update_data(request_id=request.id, photo_count=0)
    await state.set_state(NewRequestStates.awaiting_photo)
    await render(
        bot, redis, callback.message.chat.id, screens.build_photo_screen(request.display_number, 0)
    )


@router.message(NewRequestStates.awaiting_photo, F.photo)
async def receive_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
) -> None:
    data = await state.get_data()
    request_id = data["request_id"]

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    filename = f"{uuid.uuid4().hex}.jpg"
    target_dir = Path(settings.storage_root) / "requests" / str(request_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    await bot.download_file(file.file_path, destination=target_dir / filename)

    session.add(
        RequestAttachment(
            request_id=request_id,
            uploaded_by_employee_id=employee.id,
            file_path=f"requests/{request_id}/{filename}",
            content_type="image/jpeg",
        )
    )
    await session.flush()

    photo_count = data.get("photo_count", 0) + 1
    await state.update_data(photo_count=photo_count)

    request = await session.get(Request, request_id)
    await render(
        bot, redis, message.chat.id,
        screens.build_photo_screen(request.display_number, photo_count),
    )


@router.callback_query(NewRequestStates.awaiting_photo, FlowCB.filter(F.act == "photos_done"))
async def finish_photos(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    request = await session.get(Request, data["request_id"])
    await state.clear()
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_submitted_screen(
            request.display_number, data.get("photo_count", 0), request.id
        ),
    )
