import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from arq.connections import RedisSettings, create_pool
from redis.asyncio import Redis

from afu_shared.settings import settings
from app.handlers import contact, messaging, new_request, own_requests, rating, staff_requests, start, stats
from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.identity import IdentityMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    storage = RedisStorage.from_url(settings.redis_url)

    dp = Dispatcher(storage=storage)
    # Registered per-observer (not dp.update) so `event` is a real Message/CallbackQuery
    # with a `.from_user` — the raw Update object has no such attribute.
    for observer in (dp.message, dp.callback_query):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(IdentityMiddleware())

    dp.include_router(start.router)
    dp.include_router(contact.router)
    dp.include_router(new_request.router)
    dp.include_router(staff_requests.router)
    dp.include_router(messaging.router)
    dp.include_router(own_requests.router)
    dp.include_router(rating.router)
    dp.include_router(stats.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, redis=redis, arq_pool=arq_pool)


if __name__ == "__main__":
    asyncio.run(main())
