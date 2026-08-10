# database.py
import time
import random
import json
import aiosqlite
import logging
import asyncio
from config import DB_PATH, bot
from state import (
    group_custom_commands,
    user_warns,
    group_welcome_msgs,
    group_goodbye_msgs,
    group_captcha_settings,
    group_warnings_settings,
    group_log_channels,
    message_history,
    group_auto_roles,
)

logger = logging.getLogger(__name__)

# ---------- اتصال سراسری دیتابیس ----------
_db_connection = None
_db_lock = asyncio.Lock()

from functools import wraps

def async_ttl_cache(ttl=60):
    cache = {}
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key in cache:
                val, expiry = cache[key]
                if time.time() < expiry:
                    return val
                del cache[key]
            
            result = await func(*args, **kwargs)
            cache[key] = (result, time.time() + ttl)
            return result
        
        wrapper.cache_clear = lambda: cache.clear()
        return wrapper
    return decorator


async def _get_db():
    """دریافت اتصال دیتابیس (یک نمونه سراسری با قفل)"""
    global _db_connection
    async with _db_lock:
        if _db_connection is None:
            _db_connection = await aiosqlite.connect(DB_PATH)
            _db_connection.row_factory = aiosqlite.Row
            logger.info("Database connection established")
        return _db_connection


async def _execute(query, params=(), fetch_one=False, fetch_all=False):
    """اجرای کوئری با استفاده از اتصال سراسری (بدون بستن اتصال)"""
    try:
        db = await _get_db()
        async with db.execute(query, params) as cursor:
            if fetch_one:
                row = await cursor.fetchone()
                return row
            if fetch_all:
                rows = await cursor.fetchall()
                return rows
            await db.commit()
            return cursor.lastrowid
    except aiosqlite.Error as e:
        logger.error(f"Database error: {e}")
        return None


async def close_db_connection():
    """بستن اتصال دیتابیس (در هنگام خاموش شدن ربات)"""
    global _db_connection
    async with _db_lock:
        if _db_connection:
            await _db_connection.close()
            _db_connection = None
            logger.info("Database connection closed")


async def initialize_database_layers():
    """راه‌اندازی لایه‌های پایگاه داده به ترتیب امن و قابل بازاستفاده."""
    from state import init_db_advanced
    from utils import init_db_async

    await init_db_async()
    await init_db_advanced()


async def ensure_database_ready():
    """تأیید و آماده‌سازی دیتابیس قبل از استفاده در مسیرهای اصلی."""
    await initialize_database_layers()


# ==================== توابع مدیریت سطح و تجربه ====================
async def add_user_xp(chat_id, user_id, xp_amount=5):
    """اضافه کردن تجربه به کاربر"""
    get_user_level_info.cache_clear()
    current = await _execute(
        "SELECT xp, level FROM user_levels WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    
    current_time = int(time.time())
    
    if current:
        xp, level = current["xp"], current["level"]
        new_xp = xp + xp_amount
        new_level = level
        
        # محاسبه سطح جدید
        xp_needed = level * 100
        while new_xp >= xp_needed:
            new_xp -= xp_needed
            new_level += 1
            xp_needed = new_level * 100
            
            if new_level % 5 == 0:
                await award_user_badge(user_id, chat_id, f"level_{new_level}")
        
        await _execute(
            "INSERT OR REPLACE INTO user_levels (chat_id, user_id, xp, level, last_xp_time) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, new_xp, new_level, current_time)
        )
        
        if new_level > level:
            return {"level_up": True, "new_level": new_level}
    else:
        await _execute(
            "INSERT INTO user_levels (chat_id, user_id, xp, level, last_xp_time) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, xp_amount, 1, current_time)
        )
    
    return {"level_up": False}


@async_ttl_cache(ttl=300)
async def get_user_level_info(chat_id, user_id):
    """دریافت اطلاعات سطح کاربر"""
    row = await _execute(
        "SELECT xp, level FROM user_levels WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    if row:
        xp, level = row["xp"], row["level"]
        xp_needed = level * 100
        prev_xp_needed = (level - 1) * 100 if level > 1 else 0
        current_level_xp = xp - prev_xp_needed
        level_total_xp = xp_needed - prev_xp_needed
        progress = int((current_level_xp / level_total_xp) * 100) if level_total_xp > 0 else 0
        return {
            "level": level,
            "xp": xp,
            "xp_needed": xp_needed,
            "xp_remaining": xp_needed - xp,
            "progress": progress
        }
    return {"level": 1, "xp": 0, "xp_needed": 100, "xp_remaining": 100, "progress": 0}


async def get_group_leaderboard(chat_id, limit=10):
    """دریافت برترین‌های گروه"""
    rows = await _execute(
        "SELECT user_id, level, xp FROM user_levels WHERE chat_id=? ORDER BY level DESC, xp DESC LIMIT ?",
        (chat_id, limit), fetch_all=True
    )
    return [(row["user_id"], row["level"], row["xp"]) for row in rows] if rows else []


# ==================== توابع مدیریت نشان‌ها ====================
async def award_user_badge(user_id, chat_id, badge):
    """اهدای نشان به کاربر"""
    current_time = int(time.time())
    try:
        await _execute(
            "INSERT OR IGNORE INTO user_badges (user_id, chat_id, badge, earned_time) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, badge, current_time)
        )
        return True
    except Exception as e:
        logger.error(f"Error awarding badge: {e}")
        return False


async def get_user_badges(user_id, chat_id=None):
    """دریافت نشان‌های کاربر"""
    if chat_id:
        rows = await _execute(
            "SELECT badge, earned_time FROM user_badges WHERE user_id=? AND chat_id=? ORDER BY earned_time DESC",
            (user_id, chat_id), fetch_all=True
        )
        return [(row["badge"], row["earned_time"]) for row in rows] if rows else []
    else:
        rows = await _execute(
            "SELECT badge, chat_id, earned_time FROM user_badges WHERE user_id=? ORDER BY earned_time DESC",
            (user_id,), fetch_all=True
        )
        return [(row["badge"], row["chat_id"], row["earned_time"]) for row in rows] if rows else []


# ==================== توابع مدیریت دستورات سفارشی ====================
async def add_custom_command(chat_id, command, response, creator_id):
    """افزودن دستور سفارشی"""
    current_time = int(time.time())
    await _execute(
        "INSERT OR REPLACE INTO custom_commands (chat_id, command, response, created_by, created_time) VALUES (?, ?, ?, ?, ?)",
        (chat_id, command.lower(), response, creator_id, current_time)
    )
    group_custom_commands[chat_id][command.lower()] = response


async def remove_custom_command(chat_id, command):
    """حذف دستور سفارشی"""
    await _execute(
        "DELETE FROM custom_commands WHERE chat_id=? AND command=?",
        (chat_id, command.lower())
    )
    if command.lower() in group_custom_commands[chat_id]:
        del group_custom_commands[chat_id][command.lower()]


async def get_custom_command(chat_id, command):
    """دریافت پاسخ دستور سفارشی"""
    if command.lower() in group_custom_commands[chat_id]:
        return group_custom_commands[chat_id][command.lower()]
    
    row = await _execute(
        "SELECT response FROM custom_commands WHERE chat_id=? AND command=?",
        (chat_id, command.lower()), fetch_one=True
    )
    if row:
        group_custom_commands[chat_id][command.lower()] = row["response"]
        return row["response"]
    return None


async def list_custom_commands(chat_id):
    """لیست دستورات سفارشی"""
    rows = await _execute(
        "SELECT command, response, created_by FROM custom_commands WHERE chat_id=?",
        (chat_id,), fetch_all=True
    )
    return [(row["command"], row["response"], row["created_by"]) for row in rows] if rows else []


# ==================== توابع مدیریت اخطارها ====================
async def add_user_warn(chat_id, user_id, admin_id=None, reason=""):
    """افزودن اخطار به کاربر"""
    current_time = int(time.time())
    row = await _execute(
        "SELECT warn_count FROM group_warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    
    if row:
        new_count = row["warn_count"] + 1
        await _execute(
            "UPDATE group_warns SET warn_count=?, last_warn_time=? WHERE chat_id=? AND user_id=?",
            (new_count, current_time, chat_id, user_id)
        )
    else:
        new_count = 1
        await _execute(
            "INSERT INTO group_warns (chat_id, user_id, warn_count, last_warn_time) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, new_count, current_time)
        )
    
    user_warns[chat_id][user_id] = new_count
    return new_count


async def remove_user_warn(chat_id, user_id, count=1):
    """کاهش اخطار کاربر"""
    row = await _execute(
        "SELECT warn_count FROM group_warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    
    if row:
        new_count = max(0, row["warn_count"] - count)
        if new_count == 0:
            await _execute(
                "DELETE FROM group_warns WHERE chat_id=? AND user_id=?",
                (chat_id, user_id)
            )
            if user_id in user_warns[chat_id]:
                del user_warns[chat_id][user_id]
        else:
            await _execute(
                "UPDATE group_warns SET warn_count=? WHERE chat_id=? AND user_id=?",
                (new_count, chat_id, user_id)
            )
            user_warns[chat_id][user_id] = new_count
        return new_count
    return 0


async def get_user_warn_count(chat_id, user_id):
    """تعداد اخطارهای کاربر"""
    if user_id in user_warns[chat_id]:
        return user_warns[chat_id][user_id]
    
    row = await _execute(
        "SELECT warn_count FROM group_warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    if row:
        user_warns[chat_id][user_id] = row["warn_count"]
        return row["warn_count"]
    return 0


async def get_warn_settings(chat_id):
    """دریافت تنظیمات اخطار"""
    row = await _execute(
        "SELECT max_warns, action, duration FROM group_warnings_settings WHERE chat_id=?",
        (chat_id,), fetch_one=True
    )
    if row:
        return {"max_warns": row["max_warns"], "action": row["action"], "duration": row["duration"]}
    return {"max_warns": 3, "action": "mute", "duration": 3600}


async def set_warn_settings(chat_id, max_warns, action, duration):
    """تنظیمات اخطار"""
    await _execute(
        "INSERT OR REPLACE INTO group_warnings_settings (chat_id, max_warns, action, duration) VALUES (?, ?, ?, ?)",
        (chat_id, max_warns, action, duration)
    )
    group_warnings_settings[chat_id] = {"max_warns": max_warns, "action": action, "duration": duration}


# ==================== توابع مدیریت پیام خوش‌آمدگویی ====================
async def set_welcome_message(chat_id, text, media_id=None, is_active=1):
    """تنظیم پیام خوش‌آمدگویی"""
    await _execute(
        "INSERT OR REPLACE INTO group_welcome (chat_id, welcome_text, media_id, is_active) VALUES (?, ?, ?, ?)",
        (chat_id, text, media_id, is_active)
    )
    group_welcome_msgs[chat_id] = text


async def get_welcome_message(chat_id):
    """دریافت پیام خوش‌آمدگویی"""
    if chat_id in group_welcome_msgs:
        return group_welcome_msgs[chat_id]
    
    row = await _execute(
        "SELECT welcome_text FROM group_welcome WHERE chat_id=? AND is_active=1",
        (chat_id,), fetch_one=True
    )
    if row:
        group_welcome_msgs[chat_id] = row["welcome_text"]
        return row["welcome_text"]
    return None


async def set_goodbye_message(chat_id, text, media_id=None, is_active=1):
    """تنظیم پیام خداحافظی"""
    await _execute(
        "INSERT OR REPLACE INTO group_goodbye (chat_id, goodbye_text, media_id, is_active) VALUES (?, ?, ?, ?)",
        (chat_id, text, media_id, is_active)
    )
    group_goodbye_msgs[chat_id] = text


async def get_goodbye_message(chat_id):
    """دریافت پیام خداحافظی"""
    if chat_id in group_goodbye_msgs:
        return group_goodbye_msgs[chat_id]
    
    row = await _execute(
        "SELECT goodbye_text FROM group_goodbye WHERE chat_id=? AND is_active=1",
        (chat_id,), fetch_one=True
    )
    if row:
        group_goodbye_msgs[chat_id] = row["goodbye_text"]
        return row["goodbye_text"]
    return None


# ==================== توابع مدیریت کپچا ====================
async def set_captcha_settings(chat_id, is_active, difficulty="medium", kick_time=300):
    """تنظیمات کپچا"""
    await _execute(
        "INSERT OR REPLACE INTO group_captcha (chat_id, is_active, difficulty, kick_time) VALUES (?, ?, ?, ?)",
        (chat_id, 1 if is_active else 0, difficulty, kick_time)
    )
    group_captcha_settings[chat_id] = {
        "is_active": is_active,
        "difficulty": difficulty,
        "kick_time": kick_time
    }


async def get_captcha_settings(chat_id):
    """دریافت تنظیمات کپچا"""
    row = await _execute(
        "SELECT is_active, difficulty, kick_time FROM group_captcha WHERE chat_id=?",
        (chat_id,), fetch_one=True
    )
    if row and row["is_active"] == 1:
        return {"is_active": True, "difficulty": row["difficulty"], "kick_time": row["kick_time"]}
    return {"is_active": False, "difficulty": "medium", "kick_time": 300}


async def generate_captcha():
    """تولید کپچای تصادفی ارتقا یافته با ایموجی"""
    def to_emoji(num):
        mapping = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣', 
                   '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}
        return "".join(mapping.get(c, c) for c in str(num))
        
    num1 = random.randint(1, 20)
    num2 = random.randint(1, 20)
    operators = ['+', '-', '*']
    op = random.choice(operators)
    
    if op == '+':
        answer = num1 + num2
        op_str = '➕'
    elif op == '-':
        if num1 < num2:
            num1, num2 = num2, num1
        answer = num1 - num2
        op_str = '➖'
    else:
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        answer = num1 * num2
        op_str = '✖️'
        
    question = f"{to_emoji(num1)} {op_str} {to_emoji(num2)} = ❓"
    return question, answer


# ==================== توابع مدیریت نشست کپچا ====================
async def save_captcha_session(chat_id, user_id, question, answer, expires, attempts=1, message_id=None):
    """ذخیره یک نشست کپچا در دیتابیس"""
    await _execute(
        "INSERT OR REPLACE INTO captcha_sessions (chat_id, user_id, question, answer, attempts, expires, message_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, question, answer, attempts, expires, message_id)
    )


async def get_captcha_session(chat_id, user_id):
    """بازخوانی نشست کپچا از دیتابیس"""
    row = await _execute(
        "SELECT question, answer, attempts, expires, message_id FROM captcha_sessions WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    if row:
        return {
            "question": row["question"],
            "answer": row["answer"],
            "attempts": row["attempts"],
            "expires": row["expires"],
            "message_id": row["message_id"]
        }
    return None


async def delete_captcha_session(chat_id, user_id):
    """حذف نشست کپچا"""
    await _execute("DELETE FROM captcha_sessions WHERE chat_id=? AND user_id=?", (chat_id, user_id))


async def cleanup_expired_captcha_sessions():
    """پاکسازی نشست‌های منقضی‌شده (برای تسک پس‌زمینه)"""
    await _execute("DELETE FROM captcha_sessions WHERE expires < ?", (int(time.time()),))


# ==================== توابع مدیریت نظرسنجی پیشرفته ====================
async def create_advanced_poll(chat_id, question, options, created_by, is_anonymous=False, multiple_choices=False, duration=3600):
    """ایجاد نظرسنجی پیشرفته"""
    import uuid
    poll_id = str(uuid.uuid4())[:8]
    end_time = int(time.time()) + duration
    
    options_json = json.dumps(options)
    votes_json = json.dumps({str(i): [] for i in range(len(options))})
    
    await _execute(
        """INSERT INTO group_polls_advanced 
           (chat_id, poll_id, question, options, is_anonymous, multiple_choices, created_by, end_time, votes) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (chat_id, poll_id, question, options_json, 1 if is_anonymous else 0, 
         1 if multiple_choices else 0, created_by, end_time, votes_json)
    )
    
    return poll_id


async def vote_advanced_poll(chat_id, poll_id, user_id, option_indices):
    """رای دادن در نظرسنجی پیشرفته"""
    row = await _execute(
        "SELECT options, multiple_choices, votes FROM group_polls_advanced WHERE chat_id=? AND poll_id=?",
        (chat_id, poll_id), fetch_one=True
    )
    
    if not row:
        return False, "نظرسنجی یافت نشد"
    
    options_json, multiple_choices, votes_json = row["options"], row["multiple_choices"], row["votes"]
    votes = json.loads(votes_json)
    
    # حذف رای‌های قبلی کاربر
    for opt_idx in votes:
        if user_id in votes[opt_idx]:
            votes[opt_idx].remove(user_id)
    
    # افزودن رای‌های جدید
    if multiple_choices:
        for idx in option_indices:
            idx_str = str(idx)
            if idx_str in votes:
                votes[idx_str].append(user_id)
    else:
        if option_indices:
            idx_str = str(option_indices[0])
            if idx_str in votes:
                votes[idx_str].append(user_id)
    
    await _execute(
        "UPDATE group_polls_advanced SET votes=? WHERE chat_id=? AND poll_id=?",
        (json.dumps(votes), chat_id, poll_id)
    )
    
    return True, "رای شما ثبت شد"


async def get_advanced_poll_results(chat_id, poll_id):
    """نتایج نظرسنجی پیشرفته"""
    row = await _execute(
        "SELECT question, options, votes, is_anonymous, multiple_choices FROM group_polls_advanced WHERE chat_id=? AND poll_id=?",
        (chat_id, poll_id), fetch_one=True
    )
    
    if not row:
        return None
    
    question, options_json, votes_json, is_anonymous, multiple_choices = row["question"], row["options"], row["votes"], row["is_anonymous"], row["multiple_choices"]
    options = json.loads(options_json)
    votes = json.loads(votes_json)
    
    results = []
    total_votes = sum(len(v) for v in votes.values())
    
    for i, option in enumerate(options):
        vote_count = len(votes.get(str(i), []))
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
        results.append({
            "option": option,
            "votes": vote_count,
            "percentage": round(percentage, 1)
        })
    
    return {
        "question": question,
        "options": results,
        "total_votes": total_votes,
        "is_anonymous": bool(is_anonymous),
        "multiple_choices": bool(multiple_choices)
    }


# ==================== توابع مدیریت جامع گروه ====================
async def log_to_channel(chat_id, log_message):
    """ارسال لاگ به کانال ثبت"""
    if chat_id in group_log_channels:
        try:
            await bot.send_message(group_log_channels[chat_id], log_message)
        except Exception as e:
            logger.error(f"Failed to send log to channel: {e}")


async def check_spam(chat_id, user_id, text):
    """بررسی اسپم و ارسال مکرر"""
    key = f"{chat_id}:{user_id}"
    now = time.time()
    
    if key not in message_history:
        message_history[key] = []
    
    message_history[key].append(now)
    message_history[key] = [t for t in message_history[key] if now - t < 10]
    
    return len(message_history[key]) > 5


async def auto_role_check(chat_id, user_id, level):
    """اعطای نقش خودکار بر اساس سطح"""
    if chat_id not in group_auto_roles:
        rows = await _execute(
            "SELECT role_name, role_id, min_level FROM group_auto_roles WHERE chat_id=?",
            (chat_id,), fetch_all=True
        )
        if rows:
            group_auto_roles[chat_id] = {row["role_id"]: {"name": row["role_name"], "min_level": row["min_level"]} for row in rows}
    
    roles_to_add = []
    for role_id, role_info in group_auto_roles[chat_id].items():
        if level >= role_info["min_level"]:
            roles_to_add.append(role_id)
    
    return roles_to_add