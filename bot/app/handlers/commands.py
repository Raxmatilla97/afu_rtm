"""Commands and top-level navigation.

Every screen change goes through ``render`` on the anchor message, so navigating never
adds a message to the chat.
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Employee
from app.callbacks import Nav
from app.middlewares.identity import AuthState
from app.screens import assignments, menu, my_requests, new_request, stats
from app.screens.auth import show_auth_screen
from app.states.new_request import NewRequestStates
from app.ui.anchor import Screen, render
from app.utils.transient import purge_transients, send_transient

router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee | None,
    auth_state: AuthState,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await state.clear()
    await purge_transients(redis, arq_pool, message.chat.id)

    if auth_state is not AuthState.READY:
        # force_new re-anchors at the bottom so the first screen is where the user is
        # looking. Without it /start edited an anchor sitting far up the chat and the user
        # saw nothing at all — their /start was swept away by autoclean and that was that.
        await show_auth_screen(
            chat_id=message.chat.id,
            data={
                "bot": bot, "redis": redis, "arq_pool": arq_pool,
                "session": session, "auth_state": auth_state, "employee": employee,
            },
            force_new=True,
        )
        return

    assert employee is not None
    await render(bot, redis, message.chat.id, menu.build_menu(employee), force_new=True)


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, state: FSMContext, employee: Employee, bot: Bot, redis: Redis, arq_pool: ArqRedis
) -> None:
    await state.clear()
    await purge_transients(redis, arq_pool, message.chat.id)
    await render(bot, redis, message.chat.id, menu.build_menu(employee), force_new=True)


@router.message(Command("help"))
async def cmd_help(message: Message, employee: Employee, bot: Bot, redis: Redis) -> None:
    await render(bot, redis, message.chat.id, menu.build_help(employee))


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, state: FSMContext, employee: Employee, bot: Bot, redis: Redis, arq_pool: ArqRedis
) -> None:
    had_state = await state.get_state() is not None
    await state.clear()
    await purge_transients(redis, arq_pool, message.chat.id)
    await render(bot, redis, message.chat.id, menu.build_menu(employee))
    if had_state:
        await send_transient(bot, redis, arq_pool, message.chat.id, "✖️ Amal bekor qilindi.")


@router.callback_query(Nav.filter())
async def navigate(
    callback: CallbackQuery,
    callback_data: Nav,
    state: FSMContext,
    session: AsyncSession,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    # Answer first: an unanswered callback leaves a spinner on the button.
    await callback.answer()
    if callback.message is None:
        return
    chat_id = callback.message.chat.id

    target = callback_data.to
    if target == "noop":
        return

    if target != "newreq":
        await state.clear()

    screen: Screen
    if target == "menu":
        screen = menu.build_menu(employee)
    elif target == "help":
        screen = menu.build_help(employee)
    elif target == "myreq":
        screen = await my_requests.build_list(session, employee, callback_data.page)
    elif target == "assign":
        if not employee.is_rtm_staff:
            await callback.answer("Bu bo'lim faqat RTM xodimlari uchun.", show_alert=True)
            return
        screen = await assignments.build_list(session, employee, callback_data.page)
    elif target == "stats":
        screen = await stats.build_stats(session, employee)
    elif target == "newreq":
        await state.set_state(NewRequestStates.awaiting_category)
        screen = await new_request.build_category_screen(session)
    else:
        screen = menu.build_menu(employee)

    await render(bot, redis, chat_id, screen)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    """The page-indicator button. Without this the spinner hangs until Telegram times out."""
    await callback.answer()
