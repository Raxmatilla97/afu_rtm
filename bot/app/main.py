import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    MenuButtonCommands,
)
from arq.connections import RedisSettings, create_pool
from redis.asyncio import Redis

from afu_shared.settings import settings
from app.handlers import (
    assignments,
    commands,
    contact,
    fallback,
    group,
    inventory,
    messaging,
    my_requests,
    new_request,
    rating,
    replies,
    soft,
)
from app.middlewares.auth_guard import AuthGuardMiddleware
from app.middlewares.autoclean import AutoCleanMiddleware
from app.middlewares.db_session import DbSessionMiddleware
from app.middlewares.identity import IdentityMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Boshlash / qayta ishga tushirish"),
    BotCommand(command="menu", description="Asosiy menyu"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="cancel", description="Amalni bekor qilish"),
]

#: The two commands that work in a group. Shown ONLY to that chat's administrators — the
#: people who added the bot in the first place.
GROUP_ADMIN_COMMANDS = [
    BotCommand(command="rtm_on", description="Guruhga murojaatlarni ulash"),
    BotCommand(command="rtm_off", description="Guruhga murojaatlarni o'chirish"),
]

#: Ordinary group members get an empty "/" menu.
#:
#: /rtm_off silences the request feed for the whole group. Listing it in a menu that every
#: member of a forty-person chat can open is an invitation to press it; the handler refuses
#: anyone who is not RTM staff, but a refusal is still something a bored member can trigger
#: all afternoon. The commands keep working when typed — they are written down on the web
#: panel's "Admin uchun eslatmalar" page instead of advertised in the chat.
#:
#: An explicitly empty list rather than delete_my_commands: deleting a scope makes Telegram
#: fall back to the next one up, which would put /menu and /cancel — private-chat flows
#: that refuse to run in a group — in front of the whole group instead.
GROUP_COMMANDS: list[BotCommand] = []


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
    #
    # Registration order IS nesting order: the first registered wraps all the rest.
    # Autoclean therefore goes first — it must still delete the user's message when the
    # auth guard short-circuits the handler, which is exactly when an unonboarded user is
    # typing. Then a session must exist before identity is resolved, and identity before
    # the guard can judge it.
    dp.message.middleware(AutoCleanMiddleware())
    # my_chat_member carries the "bot was added to a group" event, and registering that
    # group needs both a session and the identity of whoever added it.
    for observer in (dp.message, dp.callback_query, dp.my_chat_member):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(IdentityMiddleware())
    for observer in (dp.message, dp.callback_query):
        # Not on my_chat_member: an unauthorised add is answered by the group handler
        # itself, which needs to see it rather than have it short-circuited.
        observer.middleware(AuthGuardMiddleware())

    # Group handling first, and everything else pinned to private chats. The private flows
    # are built around a per-chat anchor message and FSM state, neither of which makes sense
    # in a shared conversation — without this split a group tap would silently drive some
    # other member's half-finished form.
    dp.include_router(group.router)

    private_routers = (
        commands.router,
        contact.router,
        new_request.router,
        my_requests.router,
        assignments.router,
        inventory.router,
        soft.router,
        messaging.router,
        rating.router,
        # After the state-driven routers: someone halfway through a form who happens to
        # reply to an old notification means the form step, not a new thread message.
        replies.router,
        # Must stay last: it answers anything the routers above did not claim.
        fallback.router,
    )
    for router in private_routers:
        router.message.filter(F.chat.type == ChatType.PRIVATE)
        router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
        dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(
        GROUP_ADMIN_COMMANDS, scope=BotCommandScopeAllChatAdministrators()
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    await dp.start_polling(bot, redis=redis, arq_pool=arq_pool)


if __name__ == "__main__":
    asyncio.run(main())
