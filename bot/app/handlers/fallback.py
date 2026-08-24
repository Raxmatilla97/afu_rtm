"""Catch-all handlers. Must be the LAST router included.

Previously an unrecognized message got no reply at all, and stale callbacks (from before a
restart, or buttons whose data no longer parses) left the spinner running.
"""

import logging

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from redis.asyncio import Redis

from afu_shared.models import Employee
from app.screens import menu
from app.ui.anchor import render
from app.utils.transient import send_transient

logger = logging.getLogger(__name__)

router = Router(name="fallback")


@router.callback_query()
async def unknown_callback(
    callback: CallbackQuery, employee: Employee, bot: Bot, redis: Redis
) -> None:
    await callback.answer()
    logger.info("Unhandled callback data: %r", callback.data)
    if callback.message is not None:
        await render(bot, redis, callback.message.chat.id, menu.build_menu(employee))


@router.message()
async def unknown_message(
    message: Message,
    state: FSMContext,
    employee: Employee,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    await send_transient(
        bot, redis, arq_pool, message.chat.id,
        "Tushunmadim 🤔 Quyidagi menyudan tanlang yoki /menu ni bosing.",
    )
    # Re-anchor at the bottom so the menu is next to what the user just typed.
    await render(bot, redis, message.chat.id, menu.build_menu(employee), force_new=True)
