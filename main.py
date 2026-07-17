import asyncio
import time
import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

from config import bot, ADMIN_CHAT_ID
from utils import load_filtered_words, send_channel_reminder, init_db_async
from handler import private_handler
from manager import group_handler, check_expired_mutes
from state import user_games, init_db_advanced
from database import cleanup_expired_captcha_sessions, close_db_connection

logger = logging.getLogger(__name__)

async def cleanup_games():
    """پاک‌سازی بازی‌های ناتمام"""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired_ids = [
            gid for gid, game in user_games.items()
            if now - game.get("start_time", 0) > 120
        ]
        for gid in expired_ids:
            del user_games[gid]

async def auto_cleanup_captcha():
    """پاک‌سازی نشست‌های کپچای منقضی‌شده"""
    while True:
        await asyncio.sleep(600)  # هر ۱۰ دقیقه
        await cleanup_expired_captcha_sessions()


# نگه‌داری تسک‌های پس‌زمینه برای جلوگیری از حذف آن‌ها توسط زباله‌روب
bg_tasks = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== مقداردهی اولیه دیتابیس ==========
    await init_db_async()
    await init_db_advanced()
    
    # بارگذاری کلمات فیلتر شده
    await load_filtered_words()
    
    # ========== راه‌اندازی تسک‌های پس‌زمینه ==========
    global bg_tasks
    bg_tasks.append(asyncio.create_task(send_channel_reminder()))
    bg_tasks.append(asyncio.create_task(cleanup_games()))
    bg_tasks.append(asyncio.create_task(check_expired_mutes()))
    bg_tasks.append(asyncio.create_task(auto_cleanup_captcha()))
    
    logger.info("🤖 ربات در حالت Webhook راه‌اندازی شد...")
    logger.info(f"👑 ادمین: {ADMIN_CHAT_ID}")
    
    # ثبت آدرس وب‌هوک
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        try:
            logger.info(f"ثبت وب‌هوک در: {webhook_url}")
            await bot.set_webhook(webhook_url)
        except Exception as e:
            logger.error(f"خطا در ثبت وب‌هوک: {e}")
    else:
        logger.warning("متغیر محیطی WEBHOOK_URL تنظیم نشده است.")

    yield
    
    # خاموش شدن
    logger.info("در حال خاموش شدن...")
    for task in bg_tasks:
        task.cancel()
        
    await close_db_connection()
    logger.info("پایان تمیز ربات.")

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def rubika_webhook(request: Request):
    """دریافت آپدیت‌ها از سرور روبیکا"""
    try:
        data = await request.json()
        # پردازش آپدیت به صورت غیرهمگام تا کانکشن سریعا آزاد شود
        asyncio.create_task(bot._process_update(data))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"خطا در پردازش وب‌هوک: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"message": "Rubika Bot is running in Webhook mode!"}

if __name__ == "__main__":
    # اجرای سرور به صورت لوکال
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)