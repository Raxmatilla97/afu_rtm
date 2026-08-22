import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.enums import RequestSource, RequestStatus
from afu_shared.models import Category, Employee, Request, RequestAttachment, RequestStatusHistory
from afu_shared.settings import settings
from app.keyboards.common import BTN_NEW_REQUEST, main_menu_keyboard
from app.keyboards.requests import attach_choice_keyboard, category_keyboard, photo_done_keyboard
from app.states.new_request import NewRequestStates
from app.utils.transient import schedule_delete, send_transient

router = Router(name="new_request")


@router.message(F.text == BTN_NEW_REQUEST)
async def start_new_request(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee | None,
    arq_pool: ArqRedis,
) -> None:
    await schedule_delete(arq_pool, message.chat.id, message.message_id)

    if employee is None or not employee.is_eligible:
        await message.answer("Avval shaxsingizni tasdiqlashingiz kerak. /start ni bosing.")
        return

    categories = (
        await session.execute(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
        )
    ).scalars()
    await state.set_state(NewRequestStates.awaiting_category)
    await message.answer("Murojaat turini tanlang:", reply_markup=category_keyboard(list(categories)))


@router.callback_query(NewRequestStates.awaiting_category, F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
    category_slug = callback.data.removeprefix("cat:")
    await state.update_data(category_slug=category_slug)
    await state.set_state(NewRequestStates.awaiting_description)
    await callback.message.edit_text("Muammoni qisqacha tavsiflab bering (matn ko'rinishida):")
    await callback.answer()


@router.message(NewRequestStates.awaiting_description, F.text)
async def enter_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(NewRequestStates.awaiting_attachment_choice)
    await message.answer("Rasm yoki fayl biriktirmoqchimisiz?", reply_markup=attach_choice_keyboard())


async def _create_request(session: AsyncSession, employee: Employee, category_slug: str, description: str) -> Request:
    request = Request(
        requester_employee_id=employee.id,
        category_slug=category_slug,
        description=description,
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
    return request


@router.callback_query(NewRequestStates.awaiting_attachment_choice, F.data == "attach_no")
async def attach_no(callback: CallbackQuery, state: FSMContext, session: AsyncSession, employee: Employee) -> None:
    data = await state.get_data()
    request = await _create_request(session, employee, data["category_slug"], data["description"])
    await state.clear()
    await callback.message.edit_text(
        f"✅ Murojaatingiz qabul qilindi!\n\n№ {request.display_number}\n\nRTM xodimlari tez orada ko'rib chiqadi."
    )
    await callback.message.answer("Bosh menyu:", reply_markup=main_menu_keyboard(is_rtm_staff=employee.is_rtm_staff))
    await callback.answer()


@router.callback_query(NewRequestStates.awaiting_attachment_choice, F.data == "attach_yes")
async def attach_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession, employee: Employee) -> None:
    data = await state.get_data()
    request = await _create_request(session, employee, data["category_slug"], data["description"])
    await state.update_data(request_id=request.id, photo_count=0)
    await state.set_state(NewRequestStates.awaiting_photo)
    await callback.message.edit_text(
        f"№ {request.display_number} yaratildi. Endi rasm(lar)ni yuboring, tugagach \"✅ Tayyor\" tugmasini bosing.",
        reply_markup=photo_done_keyboard(),
    )
    await callback.answer()


@router.message(NewRequestStates.awaiting_photo, F.photo)
async def receive_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    data = await state.get_data()
    request_id = data["request_id"]

    dest_dir = Path(settings.storage_root) / "requests" / str(request_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    dest_path = dest_dir / filename

    photo = message.photo[-1]
    await message.bot.download(photo.file_id, destination=dest_path)

    session.add(
        RequestAttachment(
            request_id=request_id,
            uploaded_by_employee_id=employee.id,
            file_path=f"requests/{request_id}/{filename}",
            original_filename=filename,
            content_type="image/jpeg",
        )
    )

    photo_count = data.get("photo_count", 0) + 1
    await state.update_data(photo_count=photo_count)
    await send_transient(
        message.bot,
        redis,
        arq_pool,
        message.chat.id,
        f"📎 Rasm qabul qilindi ({photo_count} ta). Yana yuborishingiz mumkin yoki \"✅ Tayyor\"ni bosing.",
    )


@router.callback_query(NewRequestStates.awaiting_photo, F.data == "photos_done")
async def finish_photos(callback: CallbackQuery, state: FSMContext, employee: Employee) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    photo_count = data.get("photo_count", 0)
    await state.clear()

    await callback.message.edit_text(
        f"✅ Murojaatingiz qabul qilindi!\n\nRTM-{request_id:06d}\n"
        f"Biriktirilgan fayllar: {photo_count} ta\n\nRTM xodimlari tez orada ko'rib chiqadi."
    )
    await callback.message.answer("Bosh menyu:", reply_markup=main_menu_keyboard(is_rtm_staff=employee.is_rtm_staff))
    await callback.answer()
