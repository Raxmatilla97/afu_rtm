"""Handing out drivers and software.

Files are uploaded once on the web and cached by Telegram: the first send stores the
``file_id`` that comes back, and every send after that costs one API call and no upload.
A 400 MB driver therefore arrives instantly for the second person who asks, and the
server never reads it off disk again.

Everything sent here is tracked and cleared on the next screen change, and scheduled for
deletion after ten minutes regardless — the shelf is a shelf, not an archive, and a chat
full of old installers is the thing that makes people stop using the bot.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import CallbackQuery, FSInputFile
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import SoftAsset, SoftCategory
from afu_shared.settings import settings
from app.callbacks import SoftCB
from app.screens import soft as screens
from app.ui.anchor import render
from app.utils.transient import schedule_delete, send_transient, track_media

logger = logging.getLogger(__name__)

router = Router(name="soft")

#: How long a delivered file stays in the chat. Long enough to start the download on a
#: phone, short enough that the chat does not become a file manager.
FILE_TTL_SECONDS = 10 * 60


async def _categories_with_counts(session: AsyncSession) -> list[tuple[SoftCategory, int]]:
    counts = dict(
        (
            await session.execute(
                select(SoftAsset.category_slug, func.count())
                .where(SoftAsset.is_active.is_(True))
                .group_by(SoftAsset.category_slug)
            )
        ).all()
    )
    categories = list(
        (
            await session.execute(
                select(SoftCategory)
                .where(SoftCategory.is_active.is_(True))
                .order_by(SoftCategory.sort_order, SoftCategory.label_uz)
            )
        ).scalars()
    )
    return [(c, counts.get(c.slug, 0)) for c in categories]


@router.callback_query(SoftCB.filter(F.act == "cats"))
async def show_categories(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, redis: Redis
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await render(
        bot, redis, callback.message.chat.id,
        screens.build_category_screen(await _categories_with_counts(session)),
    )


@router.callback_query(SoftCB.filter(F.act == "list"))
async def show_assets(
    callback: CallbackQuery,
    callback_data: SoftCB,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    category = await session.get(SoftCategory, callback_data.slug)
    if category is None:
        return

    assets = list(
        (
            await session.execute(
                select(SoftAsset)
                .where(
                    SoftAsset.category_slug == category.slug, SoftAsset.is_active.is_(True)
                )
                .order_by(SoftAsset.title)
            )
        ).scalars()
    )
    total_pages = max(1, (len(assets) + screens.PAGE_SIZE - 1) // screens.PAGE_SIZE)
    page = min(max(1, callback_data.page), total_pages)
    start = (page - 1) * screens.PAGE_SIZE
    shown = assets[start : start + screens.PAGE_SIZE]

    # A view is "somebody had this file in front of them". This is the only screen in the
    # product where that happens, so it is the only place that counts one. Paired with
    # download_count on the web it separates a file nobody wants from one nobody finds.
    if shown:
        await session.execute(
            update(SoftAsset)
            .where(SoftAsset.id.in_([a.id for a in shown]))
            .values(view_count=SoftAsset.view_count + 1)
            # The rows in this session are only used to draw the screen, and nothing on it
            # shows the counter — so skip the extra SELECT that keeping them in step costs.
            .execution_options(synchronize_session=False)
        )

    await render(
        bot, redis, callback.message.chat.id,
        screens.build_asset_screen(category, shown, page, total_pages),
    )


@router.callback_query(SoftCB.filter(F.act == "get"))
async def send_asset(
    callback: CallbackQuery,
    callback_data: SoftCB,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
    arq_pool: ArqRedis,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    asset = await session.get(SoftAsset, callback_data.aid)
    if asset is None or not asset.is_active:
        await callback.answer("Bu fayl topilmadi.", show_alert=True)
        return

    await callback.answer("⬇️ Yuborilmoqda...")
    chat_id = callback.message.chat.id

    source: str | FSInputFile
    if asset.telegram_file_id:
        source = asset.telegram_file_id
    else:
        path = Path(settings.storage_root) / asset.file_path
        if not path.exists():
            logger.error("Soft asset %s missing on disk: %s", asset.id, path)
            await callback.answer("Fayl serverda topilmadi. RTM bilan bog'laning.", show_alert=True)
            return
        source = FSInputFile(path, filename=asset.original_filename or path.name)

    caption = f"💿 <b>{asset.title}</b>"
    if asset.version:
        caption += f" · {asset.version}"
    caption += (
        f"\n<i>🕙 {FILE_TTL_SECONDS // 60} daqiqadan so'ng bu fayl o'chiriladi — "
        "kerak bo'lsa qaytadan yuklab oling.</i>"
    )

    try:
        sent = await bot.send_document(chat_id, source, caption=caption, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramRetryAfter) as exc:
        logger.warning("Could not send soft asset %s to %s: %s", asset.id, chat_id, exc)
        return
    except TelegramBadRequest as exc:
        # A cached handle can go stale if the file was replaced. Forget it and let the next
        # press upload from disk rather than failing forever on a dead id.
        logger.warning("Soft asset %s failed to send (%s); clearing cached file id", asset.id, exc)
        asset.telegram_file_id = None
        await send_transient(
            bot, redis, arq_pool, chat_id,
            "Faylni yuborib bo'lmadi. Qaytadan urinib ko'ring.",
        )
        return

    if sent.document and not asset.telegram_file_id:
        # Cached on first delivery: from here on Telegram serves it and we never touch the
        # file again.
        asset.telegram_file_id = sent.document.file_id
    asset.download_count += 1
    asset.last_sent_at = datetime.now(timezone.utc)

    # Two independent cleanups, and both are wanted: tracking clears the file the moment
    # the user navigates anywhere, and the timer catches the case where they never do.
    await track_media(redis, chat_id, [sent.message_id])
    await schedule_delete(arq_pool, chat_id, sent.message_id, defer_seconds=FILE_TTL_SECONDS)

    category = await session.get(SoftCategory, asset.category_slug)
    if category is not None:
        assets = list(
            (
                await session.execute(
                    select(SoftAsset)
                    .where(
                        SoftAsset.category_slug == category.slug,
                        SoftAsset.is_active.is_(True),
                    )
                    .order_by(SoftAsset.title)
                )
            ).scalars()
        )
        total_pages = max(1, (len(assets) + screens.PAGE_SIZE - 1) // screens.PAGE_SIZE)
        page = min(max(1, callback_data.page), total_pages)
        start = (page - 1) * screens.PAGE_SIZE
        await render(
            bot, redis, chat_id,
            screens.build_asset_screen(
                category, assets[start : start + screens.PAGE_SIZE], page, total_pages
            ),
            # Re-anchored below the file that was just sent, and keeping it: this render is
            # the one that put it there.
            force_new=True,
            keep_media=True,
        )
