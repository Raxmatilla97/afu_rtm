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
    quick_login,
    rating,
    replies,
    soft,
)
from app.middlewares.activity import ActivityMiddleware
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
    BotCommand(command="chiqish", description="Hisobdan chiqish"),
]

#: No "/" menu in a group at all — not for members, not for that chat's administrators.
#:
#: The only two commands that work in a group are /rtm_on and /rtm_off, and both are
#: restricted to Boshliq and Admin. Telegram cannot express that as a command scope: its
#: narrowest group scope is "this chat's administrators", and a Telegram group admin is not
#: the same person as an RTM supervisor. A menu entry that refuses most of the people it is
#: shown to is worse than no menu entry — and /rtm_off silences the whole team's request
#: feed, which is not something to advertise to a forty-person chat.
#:
#: The commands still work when typed. They are written down for the people who may use
#: them on the web panel's "Admin uchun eslatmalar" page.
#:
#: An explicitly empty list rather than delete_my_commands: deleting a scope makes Telegram
#: fall back to the next one up, which would put /menu and /cancel — private-chat flows
#: that refuse to run in a group — in front of the whole group instead.
NO_GROUP_COMMANDS: list[BotCommand] = []


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
        # Inside identity (so it knows who is talking) and outside the guard (so a blocked
        # attempt still counts as somebody trying). Writes one activity row per update.
        observer.middleware(ActivityMiddleware())
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
        # Before everything else: its states own the typed lines during onboarding, and
        # a stray handler claiming a password would be both wrong and dangerous.
        quick_login.router,
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
    await bot.set_my_commands(NO_GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(
        NO_GROUP_COMMANDS, scope=BotCommandScopeAllChatAdministrators()
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    await dp.start_polling(bot, redis=redis, arq_pool=arq_pool)


if __name__ == "__main__":
    asyncio.run(main())
