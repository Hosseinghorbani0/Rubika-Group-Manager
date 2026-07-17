# manager.py - نسخه نهایی با هندلر اختصاصی ریپلای و بهینه‌سازی شده
import asyncio
import json
import logging
from datetime import datetime
import jdatetime
import random
import time
from collections import defaultdict

from rubka.asynco import Robot, Message

from config import bot
from state import user_warns

from database import (
    add_user_xp, award_user_badge, get_user_level_info, get_user_badges,
    get_user_warn_count, add_user_warn, get_warn_settings, remove_user_warn,
    set_welcome_message, get_welcome_message, set_goodbye_message, get_goodbye_message,
    set_captcha_settings, add_custom_command, remove_custom_command, list_custom_commands,
    get_group_leaderboard,
    get_captcha_settings, save_captcha_session, get_captcha_session,
    delete_captcha_session, generate_captcha as db_generate_captcha,
    _execute
)

from utils import (
    process_message_with_rules, is_first_message, save_chat_id,
    rules_fa, random_tag_text,
    get_time_info, font,
    get_currency_prices, send_request, ask_ai_question,
    ask_speaker_local, get_learning, save_learning, delete_learning,
    list_learnings, get_speaker_status, set_bot_status, get_bot_status,
    set_group_rules, get_group_rules,
    get_user_stats, get_group_stats, get_recent_messages,
    delete_messages_from_db, toggle_group_lock, add_assistant_admin,
    remove_assistant_admin, mute_user_db, unmute_user_db, get_muted_users,
    set_rule_status,
    get_antilink_status, get_chat_rules, invalidate_rules_cache,
    is_group_locked, is_muted,
    save_member, increase_message_count, get_members,
    is_assistant_admin, is_group_creator, get_group_creator, set_group_creator,
    init_rules, set_speaker_status, set_antilink_status,
    save_active_group, save_message_to_db,
    is_advertisement_name, get_user_profile, _is_member
)

from handler import process_group_commands

logger = logging.getLogger(__name__)

# ==================== قوانین اصلی برای وضعیت خلاصه ====================
MAIN_RULES = {
    "anti_ad": "📢 ضد تبلیغ",
    "anti_curse": "🤬 ضد فحش",
    "anti_hung": "⚠️ ضد هنگی",
    "anti_emoji": "😀 ضد ایموجی",
    "anti_edit": "✏️ ضد ویرایش",
    "anti_mention": "📛 ضد منشن",
    "gif": "🎬 ضد گیف",
}

# ==================== تنظیمات رگبار و اسپم ====================
RATE_LIMIT_WINDOW = 6
RATE_LIMIT_MAX_MSG = 5
PENALTY_BASE_SECONDS = 60
PENALTY_MULTIPLIER = 2
CONTENT_SPAM_THRESHOLD = 3

flood_windows: dict[str, list[float]] = defaultdict(list)
flood_penalty_count: dict[str, int] = defaultdict(int)
_flood_lock = asyncio.Lock()

content_spam_tracker: dict[str, dict] = defaultdict(lambda: {"content": None, "count": 0, "last_time": 0})
_content_lock = asyncio.Lock()

captcha_pending: set = set()
_captcha_lock = asyncio.Lock()


# ==================== توابع کمکی رگبار و اسپم ====================
async def check_rate_limit(user_id: str) -> tuple[bool, int]:
    now = time.time()
    async with _flood_lock:
        window = flood_windows[user_id]
        window[:] = [t for t in window if now - t <= RATE_LIMIT_WINDOW]
        if len(window) >= RATE_LIMIT_MAX_MSG:
            return True, len(window)
        window.append(now)
        return False, len(window) + 1


async def check_content_spam(user_id: str, content: str, content_type: str = "text") -> bool:
    async with _content_lock:
        tracker = content_spam_tracker[user_id]
        now = time.time()
        if tracker["content"] != content or (now - tracker["last_time"] > 10):
            tracker["content"] = content
            tracker["count"] = 1
            tracker["last_time"] = now
            return False
        tracker["count"] += 1
        tracker["last_time"] = now
        if tracker["count"] >= CONTENT_SPAM_THRESHOLD:
            tracker["count"] = 0
            return True
        return False


async def apply_penalty(chat_id: str, user_id: str, violation_level: int, reason: str):
    mute_seconds = PENALTY_BASE_SECONDS * (PENALTY_MULTIPLIER ** (violation_level - 1))
    await mute_user_db(chat_id, user_id, mute_seconds, is_permanent=0)
    asyncio.create_task(unmute_after_delay(chat_id, user_id, mute_seconds))
    await bot.send_message(
        chat_id,
        f"🚨 **اخطار {reason}** 🚨\n"
        f"[کاربر]({user_id}) به دلیل {reason} به مدت "
        f"{int(mute_seconds // 60)} دقیقه و {int(mute_seconds % 60)} ثانیه ساکت شد.\n"
        f"📌 مرحله تخلف: {violation_level}"
    )


async def unmute_after_delay(chat_id: str, user_id: str, delay: int):
    await asyncio.sleep(delay)
    await unmute_user_db(chat_id, user_id)
    try:
        await bot.send_message(chat_id, f"⏳ مدت سکوت [کاربر]({user_id}) تمام شد.")
    except Exception:
        pass


async def check_expired_mutes():
    while True:
        try:
            now = int(time.time())
            rows = await _execute(
                "SELECT chat_id, user_id FROM mutes WHERE is_permanent=0 AND mute_time + mute_duration <= ?",
                (now,), fetch_all=True
            )
            if rows:
                for row in rows:
                    await unmute_user_db(row["chat_id"], row["user_id"])
        except Exception as e:
            logger.error(f"خطا در پاکسازی سکوت‌های منقضی: {e}")
        await asyncio.sleep(60)


# ==================== توابع کمکی عمومی ====================
def normalize_number(text: str) -> int:
    persian_map = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    cleaned = text.strip().replace(' ', '').replace('‌', '')
    normalized = ''.join(persian_map.get(ch, ch) for ch in cleaned)
    if normalized.isdigit():
        return int(normalized)
    raise ValueError("Not a valid number")


# ==================== کپچا (فقط جمع و تفریق) ====================
async def generate_captcha():
    num1 = random.randint(1, 20)
    num2 = random.randint(1, 20)
    op = random.choice(['+', '-'])
    if op == '+':
        answer = num1 + num2
        question = f"{num1} + {num2} = ?"
    else:
        if num1 < num2:
            num1, num2 = num2, num1
        answer = num1 - num2
        question = f"{num1} - {num2} = ?"
    return question, answer


# ==================== توابع مدیریت قوانین جدید (هشتگ، فوروارد، نظرسنجی، رسانه، استیکر، تماس، لوکیشن) ====================
async def ensure_extra_rules_table():
    await _execute("""
        CREATE TABLE IF NOT EXISTS group_extra_rules (
            chat_id TEXT,
            rule_name TEXT,
            status TEXT DEFAULT 'off',
            PRIMARY KEY (chat_id, rule_name)
        )
    """)

async def get_extra_rule(chat_id: str, rule_name: str) -> bool:
    await ensure_extra_rules_table()
    row = await _execute(
        "SELECT status FROM group_extra_rules WHERE chat_id=? AND rule_name=?",
        (chat_id, rule_name), fetch_one=True
    )
    return row and row["status"] == "on"

async def set_extra_rule(chat_id: str, rule_name: str, status: bool):
    await ensure_extra_rules_table()
    status_str = "on" if status else "off"
    await _execute(
        "INSERT OR REPLACE INTO group_extra_rules (chat_id, rule_name, status) VALUES (?, ?, ?)",
        (chat_id, rule_name, status_str)
    )

# ==================== هندلر پیام ویرایش شده (ضد ویرایش) ====================
@bot.on_edited_message()
async def edited_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id

    creator = await get_group_creator(chat_id)
    if creator is None:
        return
    if await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id):
        return
    if await get_bot_status(chat_id) == "off":
        return
    if await is_muted(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    chat_rules = await get_chat_rules(chat_id)
    if chat_rules.get("anti_edit", False):
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: ویرایش پیام\n⚠️ ویرایش پیام در این گروه ممنوع است."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except Exception as e:
            logger.error(f"Error deleting edited message: {e}")


# ==================== هندلر پیام‌های فوروارد شده ====================
@bot.on_message_forwarded()
async def forwarded_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id

    creator = await get_group_creator(chat_id)
    if creator is None:
        return
    if await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id):
        return
    if await get_bot_status(chat_id) == "off":
        return
    if await is_muted(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    if await get_extra_rule(chat_id, "forward"):
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: فوروارد پیام\n⚠️ فوروارد در این گروه ممنوع است."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass


# ==================== هندلر پیام‌های نظرسنجی ====================
@bot.on_message_poll()
async def poll_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id

    creator = await get_group_creator(chat_id)
    if creator is None:
        return
    if await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id):
        return
    if await get_bot_status(chat_id) == "off":
        return
    if await is_muted(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    if await get_extra_rule(chat_id, "poll"):
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: نظرسنجی\n⚠️ ارسال نظرسنجی در این گروه ممنوع است."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass


# ==================== هندلر پیام‌های رسانه (عکس، ویدیو، گیف) ====================
@bot.on_message_media()
async def media_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id

    creator = await get_group_creator(chat_id)
    if creator is None:
        return
    if await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id):
        return
    if await get_bot_status(chat_id) == "off":
        return
    if await is_muted(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    if await get_extra_rule(chat_id, "media"):
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: ارسال رسانه (عکس/ویدیو)\n⚠️ ارسال رسانه در این گروه ممنوع است."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass


# ==================== هندلر پیام‌های استیکر ====================
@bot.on_message_sticker()
async def sticker_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id

    creator = await get_group_creator(chat_id)
    if creator is None:
        return
    if await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id):
        return
    if await get_bot_status(chat_id) == "off":
        return
    if await is_muted(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    if await get_extra_rule(chat_id, "sticker"):
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: استیکر\n⚠️ ارسال استیکر در این گروه ممنوع است."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass


# ==================== هندلر اختصاصی برای دستورات نیازمند ریپلای (ادمین) ====================
@bot.on_message_reply()
async def admin_reply_commands(bot: Robot, message: Message):
    """فقط پیام‌هایی که ریپلای شده‌اند وارد این هندلر می‌شوند (بسیار بهینه)"""
    chat_id = message.chat_id
    user_id = message.sender_id
    text = message.text or ""

    # فقط اگر کاربر ادمین است ادامه بده
    if not await is_assistant_admin(chat_id, user_id):
        return

    # دریافت اطلاعات پیام ریپلای شده مستقیماً از reply_to_message
    if not message.reply_to_message:
        await bot.send_message(chat_id, "❗ روی پیام کاربر ریپلای کنید.")
        return
    
    try:
        target_id = message.reply_to_message.sender_id
    except Exception as e:
        logger.error(f"Error getting target_id from reply_to_message: {e}")
        await bot.send_message(chat_id, "❗ نمی‌توانم فرستنده پیام ریپلای شده را پیدا کنم.")
        return

    # بن / اخراج
    if text in ["بن", "اخراج", "سیک", "بیرون", "حذف کاربر"]:
        try:
            if await bot.ban_member_chat(chat_id=chat_id, user_id=target_id):
                await bot.send_message(chat_id, f"> [کاربر]({target_id}) از گروه اخراج شد")
            else:
                await bot.send_message(chat_id, "⚠️ عملیات اخراج ناموفق بود.")
        except Exception as e:
            logger.error(f"Ban error: {e}")
            await bot.send_message(chat_id, "❗ خطا در اخراج کاربر.")
        return

    # آن بن
    elif text == "آن بن":
        try:
            if await bot.unban_chat_member(chat_id=chat_id, user_id=target_id):
                await bot.send_message(chat_id, f"[کاربر]({target_id}) از لیست بن خارج شد")
            else:
                await bot.send_message(chat_id, "⚠️ عملیات آن‌بن ناموفق بود.")
        except Exception as e:
            logger.error(f"Unban error: {e}")
            await bot.send_message(chat_id, "❗ خطا در آن‌بن کردن کاربر.")
        return

    # سکوت
    elif text.startswith("سکوت"):
        try:
            parts = text.split()
            mute_duration_seconds = 0
            is_permanent = 0
            if len(parts) == 2:
                try:
                    user_minutes = int(parts[1])
                    if user_minutes <= 0:
                        raise ValueError
                    mute_duration_seconds = user_minutes * 60
                except ValueError:
                    if parts[1].lower() == "دائمی":
                        is_permanent = 1
                    else:
                        await message.reply("❗ مدت زمان سکوت باید عدد مثبت (به دقیقه) یا 'دائمی' باشد.")
                        return
            else:
                await message.reply("❗ لطفا مدت زمان سکوت به دقیقه (عدد مثبت) یا 'دائمی' را وارد کنید.")
                return
            await mute_user_db(chat_id, target_id, mute_duration_seconds, is_permanent)
            if is_permanent:
                await message.reply(f"✅ [کاربر]({target_id}) برای همیشه سکوت شد.")
            else:
                minutes = mute_duration_seconds // 60
                await message.reply(f"✅ [کاربر]({target_id}) برای {minutes} دقیقه سکوت شد.")
                asyncio.create_task(unmute_after_delay(chat_id, target_id, mute_duration_seconds))
        except Exception as e:
            logger.error(f"Mute error: {e}")
            await message.reply("❗ خطا در پردازش درخواست سکوت.")
        return

    # حذف سکوت
    elif text == "حذف سکوت":
        try:
            await unmute_user_db(chat_id, target_id)
            await message.reply(f"🔊 سکوت [کاربر]({target_id}) برداشته شد")
        except Exception as e:
            logger.error(f"Unmute error: {e}")
            await message.reply("❗ خطا در برداشتن سکوت.")
        return

    # اخطار
    elif text == "اخطار":
        try:
            warn_count = await add_user_warn(chat_id, target_id, user_id)
            warn_settings = await get_warn_settings(chat_id)
            max_warns = warn_settings["max_warns"]
            await bot.send_message(chat_id, f"⚠️ [کاربر]({target_id}) اخطار دریافت کرد!\n📌 تعداد اخطارها: {warn_count}/{max_warns}")
            if warn_count >= max_warns:
                action = warn_settings["action"]
                duration = warn_settings["duration"]
                if action == "mute":
                    await mute_user_db(chat_id, target_id, duration)
                    await bot.send_message(chat_id, f"🔇 کاربر به دلیل {max_warns} اخطار، {duration} ثانیه سکوت شد!")
                elif action == "kick":
                    await bot.ban_member_chat(chat_id, target_id)
                    await bot.unban_chat_member(chat_id, target_id)
                    await bot.send_message(chat_id, f"👢 کاربر به دلیل {max_warns} اخطار از گروه اخراج شد!")
                elif action == "ban":
                    await bot.ban_member_chat(chat_id, target_id)
                    await bot.send_message(chat_id, f"⛔ کاربر به دلیل {max_warns} اخطار برای همیشه بن شد!")
                await _execute("DELETE FROM group_warns WHERE chat_id=? AND user_id=?", (chat_id, target_id))
                if target_id in user_warns[chat_id]:
                    del user_warns[chat_id][target_id]
        except Exception as e:
            logger.error(f"Warn error: {e}")
            await bot.send_message(chat_id, "❗ خطا در افزودن اخطار.")
        return

    # کاهش اخطار
    elif text == "کاهش اخطار":
        try:
            new_count = await remove_user_warn(chat_id, target_id)
            await bot.send_message(chat_id, f"✅ یک اخطار از [کاربر]({target_id}) کاهش یافت. اخطارهای فعلی: {new_count}")
        except Exception as e:
            logger.error(f"Reduce warn error: {e}")
            await bot.send_message(chat_id, "❗ خطا در کاهش اخطار.")
        return

    # پاکسازی اخطار
    elif text == "پاکسازی اخطار":
        try:
            await _execute("DELETE FROM group_warns WHERE chat_id=? AND user_id=?", (chat_id, target_id))
            if target_id in user_warns[chat_id]:
                del user_warns[chat_id][target_id]
            await bot.send_message(chat_id, f"✅ تمام اخطارهای [کاربر]({target_id}) پاک شد!")
        except Exception as e:
            logger.error(f"Clear warns error: {e}")
            await bot.send_message(chat_id, "❗ خطا در پاکسازی اخطار.")
        return

    # آمار کاربر
    elif text == "آمار":
        try:
            count = await get_user_stats(chat_id, target_id)
            level_info = await get_user_level_info(chat_id, target_id)
            badges = await get_user_badges(target_id, chat_id)
            warn_count = await get_user_warn_count(chat_id, target_id)
            badges_text = "، ".join([b[0] for b in badges[:5]]) if badges else "بدون نشان"
            await bot.send_message(chat_id,
                f"📊 **آمار کامل کاربر**\n\n"
                f"👤 [کاربر]({target_id})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💬 تعداد پیام‌ها: **{count}**\n"
                f"⭐ سطح: **{level_info['level']}** (تجربه: {level_info['xp']}/{level_info['xp_needed']})\n"
                f"🏅 نشان‌ها: {badges_text}\n"
                f"⚠️ اخطارها: **{warn_count}**\n"
                f"📈 پیشرفت: {level_info['progress']}%"
            )
        except Exception as e:
            logger.error(f"User stats error: {e}")
            await bot.send_message(chat_id, "❗ نتوانستم اطلاعات کاربر را دریافت کنم.")
        return


# ==================== هندلر اصلی گروه ====================
@bot.on_message_group()
async def group_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.sender_id
    text = message.text or ""

    # ---------- 1. فعال بودن ربات ----------
    creator = await get_group_creator(chat_id)
    is_active_group = creator is not None

    if not is_active_group:
        if text in ["فعال", "تنظیم ادمین", "مالک"]:
            await set_group_creator(chat_id, user_id)
            await award_user_badge(user_id, chat_id, "group_founder")
            await set_bot_status(chat_id, "on")
            await set_speaker_status(chat_id, "off")
            await set_antilink_status(chat_id, "on")
            await init_rules(chat_id)
            # مقداردهی اولیه قوانین جدید (همه خاموش)
            for rule in ["hashtag", "forward", "poll", "media", "sticker", "contact", "location"]:
                await set_extra_rule(chat_id, rule, False)
            await bot.send_message(
                chat_id,
                "✅ شما به عنوان سازنده تنظیم شدید.\n🏅 نشان «بنیانگذار گروه» به شما اهدا شد!\n"
                "🤖 ربات اکنون فعال است و پیام‌ها را بررسی می‌کند.\n"
                "🔧 قوانین جدید (هشتگ، فوروارد، نظرسنجی، رسانه، استیکر) با دستور «روشن/خاموش» قابل تنظیم هستند."
            )
            group_name = await bot.get_name(chat_id)
            group_info = {
                "name": group_name,
                "id": chat_id,
                "creator": user_id,
                "date": datetime.now().isoformat()
            }
            await save_active_group(chat_id, json.dumps(group_info))
            await save_chat_id(chat_id, "group")
            return
        else:
            return

    # ---------- 2. سکوت منقضی ----------
    if await is_muted(chat_id, user_id):
        row = await _execute(
            "SELECT mute_time, mute_duration, is_permanent FROM mutes WHERE chat_id=? AND user_id=?",
            (chat_id, user_id), fetch_one=True
        )
        if row:
            mute_time, mute_dur, is_perm = row["mute_time"], row["mute_duration"], row["is_permanent"]
            if is_perm == 0 and int(time.time()) > (mute_time + mute_dur):
                await unmute_user_db(chat_id, user_id)
            else:
                try:
                    await bot.delete_message(chat_id, message.message_id)
                except Exception:
                    pass
                return

    # ---------- 3. قفل گروه ----------
    if await is_group_locked(chat_id) and not await is_assistant_admin(chat_id, user_id):
        try:
            await bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass
        return

    # ---------- 4. رگبار و اسپم محتوایی (فقط کاربران عادی) ----------
    is_privileged = await is_assistant_admin(chat_id, user_id) or await is_group_creator(chat_id, user_id)
    if not is_privileged:
        is_rate_limited, msg_count = await check_rate_limit(user_id)
        if is_rate_limited:
            flood_penalty_count[user_id] += 1
            penalty_level = flood_penalty_count[user_id]
            await apply_penalty(chat_id, user_id, penalty_level, f"ارسال {msg_count} پیام در {RATE_LIMIT_WINDOW} ثانیه")
            try:
                await bot.delete_message(chat_id, message.message_id)
            except:
                pass
            return

        content_to_check = None
        content_type = "text"
        if message.text:
            content_to_check = message.text.strip()
        elif getattr(message, 'is_gif', False):
            content_to_check = getattr(message, 'file_id', None) or f"gif_{message.message_id}"
            content_type = "gif"
        if content_to_check:
            is_content_spam = await check_content_spam(user_id, content_to_check, content_type)
            if is_content_spam:
                flood_penalty_count[user_id] = max(flood_penalty_count[user_id], 2)
                await apply_penalty(chat_id, user_id, 2, f"ارسال مکرر {content_type} تکراری")
                try:
                    await bot.delete_message(chat_id, message.message_id)
                except:
                    pass
                return

    # ---------- 5. کپچا (سیستم حرفه‌ای) ----------
    captcha_settings = await get_captcha_settings(chat_id)
    is_verified_member = await _is_member(chat_id, user_id)

    if captcha_settings.get("is_active", False) and not is_verified_member:
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass

        session = await get_captcha_session(chat_id, user_id)
        now = int(time.time())

        if session is None or now > session.get('expires', 0):
            question, answer = await generate_captcha()
            expire_time = now + 300
            attempts = 1
            msg_text = (
                f"🔐 **تأیید امنیتی**\n"
                f"سلام [کاربر]({user_id}) عزیز!\n"
                f"لطفاً برای اثبات انسان بودن، حاصل عبارت زیر را وارد کنید:\n"
                f"🧮 **{question}**\n"
                f"⏳ مهلت: ۵ دقیقه | تلاش: {attempts}/6"
            )
            sent = await bot.send_message(chat_id, msg_text)
            await save_captcha_session(chat_id, user_id, question, answer, expire_time,
                                       attempts=attempts, message_id=sent.message_id)
            return

        user_answer_raw = text.strip()
        try:
            user_answer = normalize_number(user_answer_raw)
        except ValueError:
            session['attempts'] += 1
            if session['attempts'] >= 6:
                await mute_user_db(chat_id, user_id, mute_duration=0, is_permanent=1)
                await delete_captcha_session(chat_id, user_id)
                await bot.send_message(chat_id, f"🔇 کاربر [{user_id}] به دلیل ۶ پاسخ نامعتبر برای همیشه سکوت شد.")
            else:
                question, answer = await generate_captcha()
                expire_time = now + 300
                msg_text = (
                    f"❌ **پاسخ نامعتبر!**\n"
                    f"[کاربر]({user_id}) لطفاً فقط یک عدد وارد کنید.\n"
                    f"🧮 سوال جدید: {question}\n"
                    f"📌 تلاش: {session['attempts']}/6"
                )
                if session.get('message_id'):
                    try:
                        await bot.delete_message(chat_id, session['message_id'])
                    except:
                        pass
                sent = await bot.send_message(chat_id, msg_text)
                await save_captcha_session(chat_id, user_id, question, answer, expire_time,
                                           attempts=session['attempts'], message_id=sent.message_id)
            return

        if user_answer == session['answer']:
            await save_member(chat_id, user_id)
            await delete_captcha_session(chat_id, user_id)
            await bot.send_message(chat_id, f"✅ **تبریک** [کاربر]({user_id})! شما با موفقیت تأیید شدید و می‌توانید در گروه چت کنید.")
            welcome_msg = await get_welcome_message(chat_id)
            if welcome_msg:
                await bot.send_message(chat_id, welcome_msg)
            return
        else:
            session['attempts'] += 1
            if session['attempts'] >= 6:
                await mute_user_db(chat_id, user_id, mute_duration=0, is_permanent=1)
                await delete_captcha_session(chat_id, user_id)
                await bot.send_message(chat_id, f"🔇 کاربر [{user_id}] به دلیل ۶ پاسخ اشتباه برای همیشه سکوت شد.")
                return

            question, answer = await generate_captcha()
            expire_time = now + 300
            msg_text = (
                f"❌ **پاسخ اشتباه!**\n"
                f"[کاربر]({user_id}) پاسخ شما نادرست بود.\n"
                f"🧮 سوال جدید: {question}\n"
                f"📌 تلاش: {session['attempts']}/6"
            )
            if session.get('message_id'):
                try:
                    await bot.delete_message(chat_id, session['message_id'])
                except:
                    pass
            sent = await bot.send_message(chat_id, msg_text)
            await save_captcha_session(chat_id, user_id, question, answer, expire_time,
                                       attempts=session['attempts'], message_id=sent.message_id)
            return

    # ---------- 6. ثبت کاربر جدید (بدون کپچا) ----------
    is_new_member = not await _is_member(chat_id, user_id)
    if is_new_member:
        chat_rules = await get_chat_rules(chat_id)
        if chat_rules and chat_rules.get("anti_ad"):
            profile = await get_user_profile(user_id)
            if profile:
                full_name = profile.get('full_name', '')
                if is_advertisement_name(full_name):
                    try:
                        await bot.delete_message(chat_id, message.message_id)
                    except:
                        pass
                    await mute_user_db(chat_id, user_id, mute_duration=0, is_permanent=1)
                    await bot.send_message(
                        chat_id,
                        f"🚫 **کاربر [{full_name}]({user_id})** به دلیل داشتن نام تبلیغاتی برای همیشه ساکت شد."
                    )
                    return
        await save_member(chat_id, user_id)
    else:
        await save_member(chat_id, user_id)

    # ---------- 7. آمار و XP ----------
    await increase_message_count(chat_id, user_id)
    await save_message_to_db(chat_id, message.message_id)

    level_up = await add_user_xp(chat_id, user_id, 2)
    if level_up.get("level_up"):
        await bot.send_message(chat_id,
            f"🎉 **تبریک!**\n[کاربر]({user_id}) به سطح **{level_up['new_level']}** رسید! ✨")

    # ---------- 8. قوانین لینک و سایر قوانین پایه ----------
    antilink_status = await get_antilink_status(chat_id)
    chat_rules = await get_chat_rules(chat_id)

    # بررسی قوانین جدید در همینجا (هشتگ، شماره تماس، لوکیشن)
    violations = []
    # هشتگ
    if await get_extra_rule(chat_id, "hashtag") and message.text and "#" in message.text:
        violations.append("هشتگ")
    # شماره تماس
    if await get_extra_rule(chat_id, "contact") and hasattr(message, 'contact') and message.contact:
        violations.append("شماره تماس")
    # لوکیشن
    if await get_extra_rule(chat_id, "location") and (hasattr(message, 'location') and message.location):
        violations.append("لوکیشن")

    if violations:
        texts = "، ".join(violations)
        await bot.send_message(
            chat_id,
            f"⛔ اخطار\n> [کاربر]({user_id}) عزیز\n📌 دلیل: {texts}\n⚠️ پیام شما به دلیل نقض قوانین حذف شد."
        )
        try:
            await bot.delete_message(chat_id, message.message_id)
        except:
            pass
        return

    if await process_message_with_rules(bot, message, chat_id, chat_rules, antilink_status):
        return

    # ---------- 9. دستورات ادمین (بدون نیاز به ریپلای - فقط موارد مدیریتی دیگر) ----------
    if await is_assistant_admin(chat_id, user_id):
        # ========== حذف پیام ==========
        if text.startswith("حذف") and len(text.split()) == 2:
            try:
                num_messages = int(text.split()[1])
                num_messages = max(1, min(num_messages, 200))
            except:
                await bot.send_message(chat_id, "❗ لطفاً یک عدد معتبر وارد کنید. مثال: حذف 10")
                return
            messages_to_delete = await get_recent_messages(chat_id, num_messages)
            if not messages_to_delete:
                await bot.send_message(chat_id, "❗ هیچ پیامی برای حذف یافت نشد.")
                return
            delete_tasks = [bot.delete_message(chat_id, msg_id) for msg_id in messages_to_delete]
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)
            await delete_messages_from_db(chat_id, messages_to_delete)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            await bot.send_message(chat_id, f"✅ {success_count} از {len(messages_to_delete)} پیام اخیر حذف شد.")
            return

        # ========== قفل گروه ==========
        elif text.startswith("قفل گروه"):
            parts = text.split()
            if len(parts) >= 3 and parts[2].isdigit():
                lock_duration = int(parts[2])
                await toggle_group_lock(chat_id, 1)
                await bot.send_message(chat_id, f"✅ گروه به مدت {lock_duration} ثانیه قفل شد.")
                async def unlock_after():
                    await asyncio.sleep(lock_duration)
                    await toggle_group_lock(chat_id, 0)
                    await bot.send_message(chat_id, "✅ مدت زمان قفل گروه تمام شد. قفل گروه باز شد.")
                asyncio.create_task(unlock_after())
            else:
                await bot.send_message(chat_id, "❗ لطفا مدت زمان قفل گروه را به درستی وارد کنید.")
            return

        elif text == "باز کردن قفل گروه":
            await toggle_group_lock(chat_id, 0)
            await bot.send_message(chat_id, "✅ قفل گروه باز شد.")
            return

        # ========== افزودن/حذف ادمین (فقط سازنده) ==========
        elif text == "افزودن ادمین":
            if not await is_group_creator(chat_id, user_id):
                await bot.send_message(chat_id, "❌ فقط سازنده گروه می‌تواند ادمین اضافه کند.")
                return
            if not message.reply_to_message:
                await bot.send_message(chat_id, "❗ روی پیام کاربر ریپلای کن تا ادمین شود.")
                return
            try:
                target_id = message.reply_to_message.sender_id
                await add_assistant_admin(chat_id, target_id)
                await award_user_badge(target_id, chat_id, "group_admin")
                await bot.send_message(chat_id, f"✅ [کاربر]({target_id}) ادمین کمکی شد\n🏅 نشان «مدیر گروه» دریافت کرد!")
            except Exception as e:
                logger.error(f"Error adding admin: {e}")
                await bot.send_message(chat_id, "❗ خطا در افزودن ادمین.")
            return

        elif text == "حذف ادمین":
            if not await is_group_creator(chat_id, user_id):
                await bot.send_message(chat_id, "❌ فقط سازنده گروه می‌تواند ادمین حذف کند.")
                return
            if not message.reply_to_message:
                await bot.send_message(chat_id, "❗ روی پیام کاربر ریپلای کن تا از ادمینی حذف شود.")
                return
            try:
                target_id = message.reply_to_message.sender_id
                await remove_assistant_admin(chat_id, target_id)
                await bot.send_message(chat_id, f"❌ [کاربر]({target_id}) از ادمینی حذف شد")
            except Exception as e:
                logger.error(f"Error removing admin: {e}")
                await bot.send_message(chat_id, "❗ خطا در حذف ادمین.")
            return

        elif text == "لیست ادمین":
            rows = await _execute("SELECT user_id FROM assistant_admins WHERE chat_id=?", (chat_id,), fetch_all=True)
            if not rows:
                await bot.send_message(chat_id, "❗ ادمین کمکی وجود ندارد")
                return
            text_msg = "🛡️ **ادمین‌های کمکی :**\n\n"
            for row in rows:
                text_msg += f">- [کاربر]({row['user_id']})\n"
            await bot.send_message(chat_id, text_msg)
            return

        # ========== پاکسازی سکوت ==========
        elif text == "پاکسازی سکوت":
            await _execute("DELETE FROM mutes WHERE chat_id=?", (chat_id,))
            await bot.send_message(chat_id, "✅ **لیست سکوت با موفقیت پاک شد**")
            return

        # ========== لیست سکوت ==========
        elif text == "لیست سکوت":
            rows = await _execute(
                "SELECT user_id FROM mutes WHERE chat_id=? ORDER BY mute_time DESC LIMIT 50",
                (chat_id,), fetch_all=True
            )
            if not rows:
                await bot.send_message(chat_id, "✅ لیست سکوت خالی است")
                return
            total_count = await _execute(
                "SELECT COUNT(*) FROM mutes WHERE chat_id=?", (chat_id,), fetch_one=True
            )
            total = total_count[0] if total_count else 0
            response_text = f"🔇 **کاربران سکوت‌شده** (نمایش ۵۰ نفر از {total} نفر):\n\n"
            for row in rows:
                response_text += f">- [کاربر]({row['user_id']})\n"
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n\n⚠️ لیست بسیار طولانی است، فقط بخشی نمایش داده شد."
            await bot.send_message(chat_id, response_text)
            return

        # ========== آمار گروه ==========
        elif text == "آمار گروه":
            try:
                group_name = await bot.get_name(chat_id)
                now = jdatetime.datetime.now()
                time_text = now.strftime("%Y/%m/%d | %H:%M")
                stats = await get_group_stats(chat_id)
                leaderboard = await get_group_leaderboard(chat_id, 5)
                rows = await _execute(
                    "SELECT user_id, message_count FROM user_stats WHERE chat_id=? ORDER BY message_count DESC LIMIT 3",
                    (chat_id,), fetch_all=True
                )
                medals = ["🥇", "🥈", "🥉"]
                top_text = "\n".join(
                    f">{medals[i]} [کاربر]({row['user_id']}) — {row['message_count']} پیام" if i < len(medals) else f"> [کاربر]({row['user_id']}) — {row['message_count']} پیام"
                    for i, row in enumerate(rows or [])
                ) if rows else "هنوز کاربری وجود ندارد"
                leaderboard_text = "\n".join(
                    f"{i+1}. [کاربر]({uid}) - سطح {level} ({xp} XP)"
                    for i, (uid, level, xp) in enumerate(leaderboard)
                ) if leaderboard else "هنوز کاربری وجود ندارد"
                await bot.send_message(chat_id,
                    f"📊 **گزارش آماری — \"{group_name}\"**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🕒 **زمان :** {time_text}\n"
                    f"👥 **اعضای فعال :** {stats['active_users']}\n"
                    f"🛡️ **مدیران :** {stats['admin_count']}\n"
                    f"💬 **کل پیام‌ها :** {stats['total_messages']}\n"
                    f"🔇 **کاربران سکوت‌شده :** {stats['muted_users']}\n\n"
                    f"🏆 **مشارکت‌کنندگان برتر :**\n{top_text}\n\n"
                    f"⭐ **برترین سطوح :**\n{leaderboard_text}"
                )
            except Exception as e:
                logger.error(f"Group stats error: {e}")
                await bot.send_message(chat_id, f"⚠️ خطا در دریافت آمار گروه: {e}")
            return

        # ========== تگ کردن ==========
        elif text.startswith("تگ"):
            parts = text.split()
            chunk_size = 50
            members = []
            try:
                if len(parts) == 1:
                    rows = await _execute(
                        "SELECT user_id FROM user_stats WHERE chat_id=? ORDER BY date DESC LIMIT 300",
                        (chat_id,), fetch_all=True
                    )
                    members = [row["user_id"] for row in rows] if rows else []
                elif len(parts) >= 2:
                    if parts[1].isdigit():
                        chunk_size = min(int(parts[1]), 50)
                        rows = await _execute(
                            "SELECT user_id FROM user_stats WHERE chat_id=? ORDER BY date DESC LIMIT 300",
                            (chat_id,), fetch_all=True
                        )
                        members = [row["user_id"] for row in rows] if rows else []
                    elif parts[1] == "همه":
                        rows = await _execute(
                            "SELECT user_id FROM user_stats WHERE chat_id=? ORDER BY date DESC LIMIT 300",
                            (chat_id,), fetch_all=True
                        )
                        members = [row["user_id"] for row in rows] if rows else []
                    elif parts[1] == "ادمین":
                        creator = await get_group_creator(chat_id)
                        admins = await _execute(
                            "SELECT user_id FROM assistant_admins WHERE chat_id=?", (chat_id,), fetch_all=True
                        )
                        members_set = set()
                        if creator:
                            members_set.add(creator)
                        if admins:
                            for row in admins:
                                members_set.add(row["user_id"])
                        members = list(members_set)
                    elif parts[1] == "فعال":
                        rows = await _execute(
                            "SELECT user_id FROM user_stats WHERE chat_id=? ORDER BY message_count DESC LIMIT 300",
                            (chat_id,), fetch_all=True
                        )
                        members = [row["user_id"] for row in rows] if rows else []
                    else:
                        await bot.send_message(chat_id, "❗ پارامتر نامعتبر. از «همه»، «فعال»، «ادمین» یا یک عدد استفاده کنید.")
                        return

                if not members:
                    await bot.send_message(chat_id, "❗ کاربری برای تگ وجود ندارد")
                    return

                chunks = [members[i:i+chunk_size] for i in range(0, len(members), chunk_size)]
                for group in chunks:
                    if len(parts) > 1 and parts[1] == "ادمین":
                        text_msg = "👑 **تگ مدیران:**\n" + " , ".join(f"[ادمین]({uid})" for uid in group)
                    elif len(parts) > 1 and parts[1] == "فعال":
                        text_msg = "🔥 **تگ کاربران فعال:**\n" + " , ".join(f"[فعال]({uid})" for uid in group)
                    else:
                        text_msg = " , ".join(f"[{random_tag_text()}]({uid})" for uid in group)
                    await bot.send_message(chat_id=chat_id, text=text_msg, reply_to_message_id=message.message_id)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Tag error: {e}")
                await bot.send_message(chat_id, f"⚠️ خطا در تگ: {e}")
            return

        # ========== وضعیت قوانین (خلاصه) ==========
        elif text == "وضعیت":
            rules_status = []
            for rule, fa in MAIN_RULES.items():
                status = "✅" if chat_rules.get(rule, False) else "❌"
                rules_status.append(f"{fa}: {status}")
            antilink_icon = "✅" if antilink_status else "❌"
            antilink_text = f"🔗 ضد لینک: {antilink_icon}"
            speaker = await get_speaker_status(chat_id)
            speaker_icon = "🟢 روشن" if speaker else "🔴 خاموش"
            speaker_text = f"💬 سخنگو: {speaker_icon}"
            captcha = await get_captcha_settings(chat_id)
            captcha_icon = "🟢 روشن" if captcha.get("is_active") else "🔴 خاموش"
            captcha_text = f"🔐 کپچا: {captcha_icon}"
            state_text = "\n".join(rules_status)
            await bot.send_message(chat_id,
                f"📊 **وضعیت خلاصه قوانین گروه** --{await bot.get_name(chat_id)}-- :\n\n"
                f"{antilink_text}\n{state_text}\n\n"
                f"{speaker_text}\n{captcha_text}\n\n"
                f"⚙️ برای جزئیات کامل: **وضعیت کامل**"
            )
            return

        # ========== وضعیت کامل قوانین ==========
        elif text == "وضعیت کامل":
            all_rules_status = []
            for rule, fa in rules_fa.items():
                # تعیین وضعیت بر اساس کلید
                if rule == "link":
                    is_active = antilink_status
                elif rule in ["hashtag", "forward", "poll", "media", "sticker", "contact", "location"]:
                    is_active = await get_extra_rule(chat_id, rule)
                elif rule == "speaker":
                    is_active = await get_speaker_status(chat_id)
                elif rule == "captcha":
                    captcha_set = await get_captcha_settings(chat_id)
                    is_active = captcha_set.get("is_active", False)
                elif rule == "bot_status":
                    bot_stat = await get_bot_status(chat_id)
                    is_active = (bot_stat == "on")
                elif rule == "group_lock":
                    is_active = await is_group_locked(chat_id)
                else:
                    # قوانین عادی مثل anti_ad, anti_curse, ...
                    is_active = chat_rules.get(rule, False)
                
                status_emoji = "✅" if is_active else "❌"
                all_rules_status.append(f"{fa}: {status_emoji}")
            
            full_text = "\n".join(all_rules_status)
            await bot.send_message(
                chat_id,
                f"📊 **وضعیت کامل قوانین و تنظیمات گروه** --{await bot.get_name(chat_id)}-- :\n\n{full_text}\n\n"
                f"⚙️ برای تغییر وضعیت قوانین، از دستورهای مرتبط استفاده کنید."
            )
            return

        # ========== خاموش/روشن همه ==========
        elif text == "خاموش همه":
            for rule, fa in rules_fa.items():
                if rule in ["hashtag", "forward", "poll", "media", "sticker", "contact", "location"]:
                    await set_extra_rule(chat_id, rule, False)
                elif rule == "speaker":
                    await set_speaker_status(chat_id, "off")
                elif rule == "captcha":
                    await set_captcha_settings(chat_id, False)
                elif rule == "bot_status":
                    await set_bot_status(chat_id, "off")
                elif rule == "group_lock":
                    await toggle_group_lock(chat_id, 0)
                else:
                    await set_rule_status(chat_id, rule, "off")
            await invalidate_rules_cache(chat_id)
            await bot.send_message(chat_id, "🔕 همه قوانین خاموش شدند")
            return

        elif text == "روشن همه":
            for rule, fa in rules_fa.items():
                if rule in ["hashtag", "forward", "poll", "media", "sticker", "contact", "location"]:
                    await set_extra_rule(chat_id, rule, True)
                elif rule == "speaker":
                    await set_speaker_status(chat_id, "on")
                elif rule == "captcha":
                    await set_captcha_settings(chat_id, True)
                elif rule == "bot_status":
                    await set_bot_status(chat_id, "on")
                elif rule == "group_lock":
                    await toggle_group_lock(chat_id, 1)
                else:
                    await set_rule_status(chat_id, rule, "on")
            await invalidate_rules_cache(chat_id)
            await bot.send_message(chat_id, "🔔 همه قوانین روشن شدند")
            return

        # ========== تنظیم اخطار ==========
        elif text.startswith("تنظیم اخطار"):
            try:
                # حذف "تنظیم اخطار" و جدا کردن با خط تیره
                rest = text.replace("تنظیم اخطار", "").strip()
                if not rest.startswith("-"):
                    # فرمت قدیمی (بدون خط تیره) برای سازگاری
                    parts = text.split()
                    if len(parts) >= 4:
                        max_warns = int(parts[2])
                        action = parts[3].lower()
                        duration = int(parts[4]) if len(parts) > 4 else 3600
                    else:
                        await bot.send_message(chat_id, "❌ فرمت صحیح: تنظیم اخطار - [تعداد] - [نوع] - [مدت]\nمثال: تنظیم اخطار - 3 - سکوت - 60")
                        return
                else:
                    # جدا کردن با خط تیره
                    parts = [p.strip() for p in rest.split("-") if p.strip()]
                    if len(parts) < 2:
                        await bot.send_message(chat_id, "❌ فرمت صحیح: تنظیم اخطار - [تعداد] - [نوع] - [مدت]\nمثال: تنظیم اخطار - 3 - سکوت - 60")
                        return
                    max_warns = normalize_number(parts[0])
                    action_raw = parts[1].lower()
                    duration = normalize_number(parts[2]) if len(parts) > 2 else 3600
                    
                    action_map = {
                        "سکوت": "mute",
                        "اخراج": "kick",
                        "بن": "ban",
                        "هیچ": "none"
                    }
                    action = action_map.get(action_raw, action_raw)
                    if action not in ["mute", "kick", "ban", "none"]:
                        await bot.send_message(chat_id, "❌ نوع جریمه باید یکی از: سکوت، اخراج، بن، هیچ")
                        return
                
                await set_warn_settings(chat_id, max_warns, action, duration)
                action_fa = {"mute": "سکوت", "kick": "اخراج", "ban": "بن", "none": "هیچ"}.get(action, action)
                await bot.send_message(chat_id,
                    f"✅ تنظیمات اخطار بروزرسانی شد:\nحداکثر اخطار: {max_warns}\nجریمه: {action_fa}\nمدت: {duration} ثانیه")
            except ValueError:
                await bot.send_message(chat_id, "❌ لطفاً اعداد را صحیح وارد کنید (مثال: 3 یا ۳)")
            except Exception as e:
                logger.error(f"Error in set warn: {e}")
                await bot.send_message(chat_id, f"❌ خطا در تنظیم اخطار: {str(e)}")
            return

        # ========== پیام خوشامد/خداحافظ ==========
        elif text.startswith("پیام خوشامد"):
            welcome_text = text.replace("پیام خوشامد", "").strip()
            if welcome_text:
                await set_welcome_message(chat_id, welcome_text)
                await bot.send_message(chat_id, f"✅ پیام خوش‌آمدگویی تنظیم شد:\n{welcome_text}")
            else:
                current = await get_welcome_message(chat_id)
                if current:
                    await bot.send_message(chat_id, f"📝 پیام خوش‌آمدگویی فعلی:\n{current}")
                else:
                    await bot.send_message(chat_id, "❌ پیام خوش‌آمدگویی تنظیم نشده است.")
            return

        elif text.startswith("پیام خداحافظ"):
            goodbye_text = text.replace("پیام خداحافظ", "").strip()
            if goodbye_text:
                await set_goodbye_message(chat_id, goodbye_text)
                await bot.send_message(chat_id, f"✅ پیام خداحافظی تنظیم شد:\n{goodbye_text}")
            else:
                current = await get_goodbye_message(chat_id)
                if current:
                    await bot.send_message(chat_id, f"📝 پیام خداحافظی فعلی:\n{current}")
                else:
                    await bot.send_message(chat_id, "❌ پیام خداحافظی تنظیم نشده است.")
            return

        # ========== کپچا روشن/خاموش ==========
        elif text == "کپچا روشن":
            await set_captcha_settings(chat_id, True)
            await bot.send_message(chat_id, "✅ سیستم کپچا روشن شد.")
            return
        elif text == "کپچا خاموش":
            await set_captcha_settings(chat_id, False)
            await bot.send_message(chat_id, "❌ سیستم کپچا خاموش شد.")
            return

        # ========== دستورات سفارشی ==========
        elif text.startswith("دستور جدید"):
            parts = text.split(" ", 3)
            if len(parts) >= 4:
                cmd = parts[2]
                response = parts[3]
                await add_custom_command(chat_id, cmd, response, user_id)
                await bot.send_message(chat_id, f"✅ دستور جدید «{cmd}» با موفقیت اضافه شد!")
            else:
                await bot.send_message(chat_id, "❌ فرمت صحیح: دستور جدید !cmd پاسخ")
            return
        elif text.startswith("حذف دستور"):
            parts = text.split(" ")
            if len(parts) >= 3:
                cmd = parts[2]
                await remove_custom_command(chat_id, cmd)
                await bot.send_message(chat_id, f"✅ دستور «{cmd}» حذف شد!")
            else:
                await bot.send_message(chat_id, "❌ فرمت صحیح: حذف دستور !cmd")
            return
        elif text == "لیست دستورات":
            commands = await list_custom_commands(chat_id)
            if commands:
                msg = "📋 **دستورات سفارشی گروه:**\n\n"
                for cmd, resp, creator in commands[:20]:
                    msg += f"🔹 {cmd}: {resp[:30]}...\n"
                await bot.send_message(chat_id, msg)
            else:
                await bot.send_message(chat_id, "📭 هیچ دستور سفارشی‌ای تعریف نشده است.")
            return

        # ========== قفل تکی قوانین (برای قوانین جدید هم اضافه شد) ==========
        if text.startswith("قفل "):
            rule_fa = text[4:].strip()  # remove "قفل "
            matched = False
            for rule, fa in rules_fa.items():
                if rule_fa == fa:
                    if rule in ["hashtag", "forward", "poll", "media", "sticker", "contact", "location"]:
                        current = await get_extra_rule(chat_id, rule)
                        await set_extra_rule(chat_id, rule, not current)
                        status_text = "فعال" if not current else "غیرفعال"
                        await bot.send_message(chat_id, f"✔️ وضعیت **{fa}** {status_text} شد")
                    else:
                        current_status = chat_rules.get(rule, True)
                        new_status = "off" if current_status else "on"
                        await set_rule_status(chat_id, rule, new_status)
                        await invalidate_rules_cache(chat_id)
                        status_text = "فعال" if new_status == "on" else "غیرفعال"
                        await bot.send_message(chat_id, f"✔️ وضعیت **{fa}** {status_text} شد")
                    matched = True
                    break
            if not matched:
                await bot.send_message(chat_id, "❌ نام قانون نامعتبر است.")
            return

        # ========== رفع سکوت دائمی کپچا (فقط سازنده) ==========
        elif text.startswith("معاف-"):
            if not await is_group_creator(chat_id, user_id):
                await bot.send_message(chat_id, "❌ فقط سازنده گروه می‌تواند از این دستور استفاده کند.")
                return
            parts = text.split("-", 1)
            if len(parts) != 2 or not parts[1].strip():
                await bot.send_message(chat_id, "❌ فرمت صحیح: معاف-<user_id>\nمثال: معاف-u0FKEeZ0f9515b286b7180fce1ef60b1")
                return
            target_id = parts[1].strip()
            await unmute_user_db(chat_id, target_id)
            await delete_captcha_session(chat_id, target_id)
            await _execute("DELETE FROM members WHERE chat_id=? AND user_id=?", (chat_id, target_id))
            await bot.send_message(chat_id, f"✅ کاربر [کاربر]({target_id}) از سکوت دائمی خارج شد و می‌تواند دوباره در گروه فعالیت کند.\n🔄 در صورت نیاز، دفعه بعد که پیام بفرستد کپچا دریافت خواهد کرد.")
            return

    # ---------- 10. دستورات عمومی ----------
    if await process_group_commands(bot, message, chat_id, user_id, text):
        return

    # ---------- 11. یادگیری ----------
    learned = await get_learning(chat_id, text)
    if learned:
        await message.reply(learned)
        return

    # ---------- 12. سخنگو ----------
    if await get_speaker_status(chat_id):
        response = await ask_speaker_local(text)
        if response:
            await message.reply(response)