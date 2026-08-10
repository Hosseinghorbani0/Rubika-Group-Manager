

import asyncio
import time
import logging
import signal

from config import bot, ADMIN_CHAT_ID
from utils import load_filtered_words, send_channel_reminder, init_db_async
from handler import private_handler
from manager import group_handler, check_expired_mutes
from state import user_games, init_db_advanced
from database import cleanup_expired_captcha_sessions, close_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ========================= Background Tasks =========================

async def cleanup_games():
    """پاک‌سازی بازی‌های ناتمام هر دقیقه"""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired_ids = [
            gid for gid, game in user_games.items()
            if now - game.get("start_time", 0) > 120
        ]
        for gid in expired_ids:
            del user_games[gid]
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired games.")


async def auto_cleanup_captcha():
    """پاک‌سازی نشست‌های کپچای منقضی هر ۱۰ دقیقه"""
    while True:
        await asyncio.sleep(600)
        await cleanup_expired_captcha_sessions()
        logger.info("Captcha sessions cleaned up.")


# ========================= Graceful Shutdown =========================

async def shutdown(loop):
    """پایان تمیز ربات هنگام دریافت سیگنال خروج"""
    logger.info("Received shutdown signal, stopping bot...")
    await close_db_connection()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()
    logger.info("Bot stopped cleanly.")


# ========================= Main Entry Point =========================

async def main():
    # 1. مقداردهی اولیه دیتابیس
    await init_db_async()
    await init_db_advanced()

    # 2. بارگذاری کلمات فیلتر‌شده
    await load_filtered_words()

    # 3. اجرای تسک‌های پس‌زمینه
    tasks = [
        asyncio.create_task(send_channel_reminder()),
        asyncio.create_task(cleanup_games()),
        asyncio.create_task(check_expired_mutes()),
        asyncio.create_task(auto_cleanup_captcha()),
    ]

    logger.info("🤖 Bot starting in Webhook mode (PHP Bridge)...")
    logger.info(f"👑 Admin: {ADMIN_CHAT_ID}")

    # 4. ثبت signal handler برای خاموش‌شدن تمیز (Linux)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop)))
        except NotImplementedError:
            # ویندوز این را پشتیبانی نمی‌کند
            pass

    # 5. اجرای ربات
    # rubka خودش از پارامتر web_hook استفاده می‌کند؛
    # هنگام start، endpoint ها را ثبت می‌کند و سپس در حالت polling
    # آپدیت‌هایی که از webhook.php می‌آیند را پردازش می‌کند.
    try:
        await bot.run()
    finally:
        await close_db_connection()
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("All background tasks stopped.")


if __name__ == "__main__":
    asyncio.run(main())