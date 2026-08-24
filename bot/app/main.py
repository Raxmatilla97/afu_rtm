import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, MenuButtonCommands
from arq.connections import RedisSettings, create_pool
from redis.asyncio import Redis

from afu_shared.settings import settings
from app.handlers import (
    assignments,
    commands,
    contact,
    fallback,
    messaging,
    my_requests,
    new_request,
    rating,
)
from app.middlewares.auth_guard import AuthGuardMiddleware
from app.middlewares.autoclean import AutoCleanMiddleware
from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.identity import IdentityMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="menu", description="Asosiy menyu"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="cancel", description="Amalni bekor qilish"),
]


async def main() -> None:
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    storage = RedisStorage.from_url(settings.redis_url)

    dp = Dispatcher(storage=storage)

    # Registered per-observer rather than on dp.update, because `event` must be a real
    # Message/CallbackQuery — the raw Update object has no `.from_user`.
    # Order matters: a session must exist before identity is resolved, identity before the
    # guard can judge it, and autoclean runs outermost so it still fires when the guard
    # short-circuits the handler.
    for observer in (dp.message, dp.callback_query):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(IdentityMiddleware())
        observer.middleware(AuthGuardMiddleware())
    dp.message.middleware(AutoCleanMiddleware())

    dp.include_router(commands.router)
    dp.include_router(contact.router)
    dp.include_router(new_request.router)
    dp.include_router(my_requests.router)
    dp.include_router(assignments.router)
    dp.include_router(messaging.router)
    dp.include_router(rating.router)
    # Must stay last: it answers anything the routers above did not claim.
    dp.include_router(fallback.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    await dp.start_polling(bot, redis=redis, arq_pool=arq_pool)


if __name__ == "__main__":
    asyncio.run(main())
