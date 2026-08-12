# utils.py
import random
import time
import re
import asyncio
import ast
import httpx
import json
import logging
from pathlib import Path
from bs4 import BeautifulSoup
import aiosqlite
from rubka.button import InlineBuilder, ChatKeypadBuilder
from rubka.asynco import Robot, Message
from config import DB_PATH, ADMIN_CHAT_ID, CHANNEL_LINK, CHANNEL_CREATOR, AI_API_URL, bot
from database import _execute  # استفاده از تابع مشترک دیتابیس

# ------------------ راه‌اندازی logging ------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ------------------ بارگذاری داده‌ها از JSON ------------------
DATA_DIR = Path(__file__).parent / "data"

def load_json(filename):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

speaker_db = load_json("speaker_db.json")
rules_fa = load_json("rules_fa.json")
TAG_TEXTS = load_json("tag_texts.json")
challenge_list = load_json("challenges.json")
hadiths = load_json("hadiths.json")
memories = load_json("memories.json")
stories = load_json("stories.json")

# ------------------ متغیرها و الگوهای فنی ------------------
filtered_words_by_chat = {}
ad_patterns = [
    r'بی[\.\/]*و',
    r'ل[\.\/]*ی[\.\/]*ن[\.\/]*ک',
    r'ع[\.\/]*ض[\.\/]*و',
    r'ج[\.\/]*و[\.\/]*ی[\.\/]*ن',
    r'پ[\.\/]*ی',
    r'س[\.\/]*ر[\.\/]*ی[\.\/]*ع',
    r'ب[\.\/]*ر[\.\/]*ن[\.\/]*ا[\.\/]*م[\.\/]*ه',
    r'چ[\.\/]*ت',
    r'چ[\.\/]*ک',
    r'ت[\.\/]*ب[\.\/]*ل[\.\/]*ی[\.\/]*غ'
]
hung_patterns = [
    r'1\.1\.1\.1\.1\.1\.1', r'2\.2\.2\.2\.2', r'1\.2\.3\.1\.2\.3',
    r'0\.0\.0\.0\.', r'5\.5\.5\.5', r'6\.6\.0\.3',
    r'Filter', r'Ban', r'report'
]
# ایموجی‌های معمولاً اسپم
emoji_list = "🔥👎✨🖿😐🙂😂♥️🫸🥸💰😑😌😒🥲💋🚶🏻‍♂️😘👍🤲🖕💎✅💕🤌🫷🤣👇😡🚫❓❔🙘😅👏🥳😭😅🥲😪😛🤗🥱☹️🤮🤢😈👻🌚🌝💩😹😻😼😽😹😿❤️🧡💛💚🩵💙🩹👀💀🦴🦷🐨🐼🐹🐭🐰🦊🦝🐻🐮🐷🦁🐜🐱🐶🐘🦍🍎🍉🍑🍊🥭🍝🍌🍐🍸🍋🍋🥝🫒🍇🍕🍭🍬🍫🧸"
AD_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in ad_patterns]
HUNG_PATTERNS_COMPILED = [re.compile(p) for p in hung_patterns]
EMOJI_SET = frozenset(emoji_list)

group_rules_cache = {}

def _load_curse_words_once():
    try:
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("fohshs", "fohshs.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(getattr(mod, "curse_words", []))
    except Exception as e:
        logger.error(f"Error loading curse words: {e}")
    return []

CURSE_WORDS = _load_curse_words_once()
CURSE_WORDS_SET = set(CURSE_WORDS)  # برای جستجوی سریع


# ------------------ توابع راه‌اندازی اولیه ------------------
async def init_db_async():
    """ایجاد جداول مورد نیاز با aiosqlite (در صورت عدم وجود)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS chats (chat_id TEXT PRIMARY KEY, type TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admins (chat_id TEXT PRIMARY KEY, creator_id TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS speaker_status (chat_id TEXT PRIMARY KEY, status TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS antilink (chat_id TEXT PRIMARY KEY, status TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS learn (chat_id TEXT, question TEXT, answer TEXT, PRIMARY KEY (chat_id, question))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS rules (
            chat_id TEXT PRIMARY KEY, 
            anti_ad TEXT DEFAULT 'on',
            anti_curse TEXT DEFAULT 'on',
            anti_hung TEXT DEFAULT 'on',
            anti_emoji TEXT DEFAULT 'on',
            anti_edit TEXT DEFAULT 'on',
            anti_mention TEXT DEFAULT 'on',
            gif TEXT DEFAULT 'on'
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS filtered_words (chat_id TEXT, word TEXT, PRIMARY KEY (chat_id, word))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS users (chat_id TEXT, user_id TEXT PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS mutes (chat_id TEXT, user_id TEXT, mute_time INTEGER, mute_duration INTEGER, is_permanent INTEGER, PRIMARY KEY (chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS members (chat_id TEXT, user_id TEXT, PRIMARY KEY (chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_stats (chat_id TEXT, user_id TEXT, message_count INTEGER DEFAULT 0, date INTEGER, PRIMARY KEY (chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS group_lock (chat_id TEXT PRIMARY KEY, is_locked INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS assistant_admins (chat_id TEXT, user_id TEXT, PRIMARY KEY (chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, message_id INTEGER, timestamp INTEGER, PRIMARY KEY (chat_id, message_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS group_rules_text (chat_id TEXT PRIMARY KEY, rules_text TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS bot_status_chat (chat_id TEXT PRIMARY KEY, status TEXT DEFAULT 'on')""")
        await db.execute("""CREATE TABLE IF NOT EXISTS active_groups (chat_id TEXT PRIMARY KEY, group_info TEXT)""")
        await db.commit()
    logger.info("Database initialized (async)")

def init_db_sync():
    """تابع همگام (فقط برای سازگاری)"""
    pass

# ------------------ توابع کمکی دیتابیسی ------------------
async def load_filtered_words():
    global filtered_words_by_chat
    rows = await _execute("SELECT chat_id, word FROM filtered_words", fetch_all=True)
    if rows:
        for row in rows:
            chat_id = row["chat_id"]
            word = row["word"]
            if chat_id not in filtered_words_by_chat:
                filtered_words_by_chat[chat_id] = set()
            filtered_words_by_chat[chat_id].add(word.lower())

async def is_first_message(chat_id):
    result = await _execute("SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,), fetch_one=True)
    return result is None

async def save_chat_id(chat_id, chat_type):
    await _execute("INSERT OR IGNORE INTO chats (chat_id, type) VALUES (?, ?)", (chat_id, chat_type))

async def set_group_creator(chat_id, creator_id):
    await _execute("INSERT OR REPLACE INTO admins (chat_id, creator_id) VALUES (?, ?)", (chat_id, creator_id))

async def get_group_creator(chat_id):
    row = await _execute("SELECT creator_id FROM admins WHERE chat_id = ?", (chat_id,), fetch_one=True)
    return row["creator_id"] if row else None

async def is_group_creator(chat_id, user_id):
    creator = await get_group_creator(chat_id)
    return str(user_id) == str(creator)

async def set_speaker_status(chat_id, status):
    await _execute("INSERT OR REPLACE INTO speaker_status (chat_id, status) VALUES (?, ?)", (chat_id, status))

async def get_speaker_status(chat_id):
    row = await _execute("SELECT status FROM speaker_status WHERE chat_id = ?", (chat_id,), fetch_one=True)
    return row and row["status"] == "on"

async def save_learning(chat_id, question, answer):
    await _execute("INSERT OR REPLACE INTO learn (chat_id, question, answer) VALUES (?, ?, ?)", (chat_id, question.strip(), answer.strip()))

async def get_learning(chat_id, text):
    row = await _execute("SELECT answer FROM learn WHERE chat_id = ? AND question = ?", (chat_id, text.strip()), fetch_one=True)
    return row["answer"] if row else None

async def delete_learning(chat_id, question):
    await _execute("DELETE FROM learn WHERE chat_id = ? AND question = ?", (chat_id, question.strip()))

async def list_learnings(chat_id):
    rows = await _execute("SELECT question, answer FROM learn WHERE chat_id = ?", (chat_id,), fetch_all=True)
    return [(row["question"], row["answer"]) for row in rows] if rows else []

async def get_counts():
    groups = await _execute("SELECT COUNT(*) FROM chats WHERE type='group'", fetch_one=True)
    users = await _execute("SELECT COUNT(*) FROM chats WHERE type='private'", fetch_one=True)
    return (groups[0] if groups else 0), (users[0] if users else 0)

async def get_total_count():
    total = await _execute("SELECT COUNT(*) FROM chats", fetch_one=True)
    return total[0] if total else 0

async def get_all_chats():
    result = await _execute("SELECT chat_id FROM chats", fetch_all=True)
    return [row["chat_id"] for row in result] if result else []

async def set_antilink_status(chat_id, status):
    await _execute("INSERT OR REPLACE INTO antilink (chat_id, status) VALUES (?, ?)", (chat_id, status))

async def get_antilink_status(chat_id):
    row = await _execute("SELECT status FROM antilink WHERE chat_id = ?", (chat_id,), fetch_one=True)
    return row and row["status"] == "on"

# ------------------ مدیریت قوانین با کش ------------------
async def get_chat_rules(chat_id):
    if chat_id in group_rules_cache:
        return group_rules_cache[chat_id]
    row = await _execute("SELECT * FROM rules WHERE chat_id=?", (chat_id,), fetch_one=True)
    if not row:
        rules = {
            "anti_ad": True, "anti_curse": True, "anti_hung": True,
            "anti_emoji": True, "anti_edit": True, "anti_mention": True, "gif": True
        }
        group_rules_cache[chat_id] = rules
        return rules
    else:
        columns = ["anti_ad", "anti_curse", "anti_hung", "anti_emoji", "anti_edit", "anti_mention", "gif"]
        rules = {col: (row[col] == "on") for col in columns}
        group_rules_cache[chat_id] = rules
        return rules

async def invalidate_rules_cache(chat_id):
    group_rules_cache.pop(chat_id, None)

async def get_rule_status(chat_id, rule_type):
    rules = await get_chat_rules(chat_id)
    return rules.get(rule_type, False)

async def set_rule_status(chat_id, rule_type, status):
    columns = ["anti_ad", "anti_curse", "anti_hung", "anti_emoji", "anti_edit", "anti_mention", "gif"]
    if rule_type not in columns:
        return
    row = await _execute("SELECT * FROM rules WHERE chat_id=?", (chat_id,), fetch_one=True)
    if row:
        await _execute(f"UPDATE rules SET {rule_type}=? WHERE chat_id=?", (status, chat_id))
    else:
        vals = {col: "on" for col in columns}
        vals[rule_type] = status
        placeholders = ", ".join(vals.keys())
        params = [chat_id] + list(vals.values())
        await _execute(f"INSERT INTO rules (chat_id, {placeholders}) VALUES ({','.join(['?']*len(params))})", params)
    await invalidate_rules_cache(chat_id)

async def init_rules(chat_id):
    await _execute(
        "INSERT OR REPLACE INTO rules (chat_id, anti_ad, anti_curse, anti_hung, anti_emoji, anti_edit, anti_mention, gif) "
        "VALUES (?, 'on', 'on', 'on', 'off', 'on', 'off', 'off')", (chat_id,)
    )
    await invalidate_rules_cache(chat_id)

# ------------------ توابع فیلتر و مدیریت ------------------
async def add_filtered_word(chat_id, word):
    await _execute("INSERT OR IGNORE INTO filtered_words (chat_id, word) VALUES (?, ?)", (chat_id, word))
    if chat_id not in filtered_words_by_chat:
        filtered_words_by_chat[chat_id] = set()
    filtered_words_by_chat[chat_id].add(word.lower())

async def remove_filtered_word(chat_id, word):
    await _execute("DELETE FROM filtered_words WHERE chat_id = ? AND word = ?", (chat_id, word))
    if chat_id in filtered_words_by_chat:
        filtered_words_by_chat[chat_id].discard(word.lower())

async def get_filtered_words(chat_id):
    return list(filtered_words_by_chat.get(chat_id, set()))

async def add_assistant_admin(chat_id, user_id):
    await _execute("INSERT OR IGNORE INTO assistant_admins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))

async def remove_assistant_admin(chat_id, user_id):
    await _execute("DELETE FROM assistant_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))

async def is_assistant_admin(chat_id, user_id):
    if await is_group_creator(chat_id, user_id):
        return True
    row = await _execute("SELECT 1 FROM assistant_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id), fetch_one=True)
    return row is not None

async def toggle_group_lock(chat_id, is_locked):
    await _execute("INSERT OR REPLACE INTO group_lock (chat_id, is_locked) VALUES (?, ?)", (chat_id, is_locked))

async def is_group_locked(chat_id):
    row = await _execute("SELECT is_locked FROM group_lock WHERE chat_id=?", (chat_id,), fetch_one=True)
    return row and row["is_locked"] == 1

async def save_member(chat_id, user_id):
    await _execute("INSERT OR IGNORE INTO members (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))

async def get_members(chat_id):
    rows = await _execute("SELECT user_id FROM members WHERE chat_id=?", (chat_id,), fetch_all=True)
    return [row["user_id"] for row in rows] if rows else []

async def increase_message_count(chat_id, user_id):
    await _execute("""
    INSERT INTO user_stats (chat_id, user_id, message_count, date)
    VALUES (?, ?, 1, ?)
    ON CONFLICT(chat_id, user_id)
    DO UPDATE SET message_count = message_count + 1, date = ?
    """, (chat_id, user_id, int(time.time()), int(time.time())))

async def mute_user_db(chat_id, user_id, mute_duration=0, is_permanent=0):
    await _execute("""
    INSERT OR REPLACE INTO mutes (chat_id, user_id, mute_time, mute_duration, is_permanent)
    VALUES (?, ?, ?, ?, ?)
    """, (chat_id, user_id, int(time.time()), mute_duration, is_permanent))

async def unmute_user_db(chat_id, user_id):
    await _execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (chat_id, user_id))

async def is_muted(chat_id, user_id):
    row = await _execute("SELECT 1 FROM mutes WHERE chat_id=? AND user_id=?", (chat_id, user_id), fetch_one=True)
    return row is not None

async def get_muted_users(chat_id):
    rows = await _execute("SELECT user_id FROM mutes WHERE chat_id=?", (chat_id,), fetch_all=True)
    return [row["user_id"] for row in rows] if rows else []

async def get_user_stats(chat_id, user_id):
    row = await _execute("SELECT message_count FROM user_stats WHERE chat_id=? AND user_id=?", (chat_id, user_id), fetch_one=True)
    return row["message_count"] if row else 0

async def get_group_stats(chat_id):
    total_messages = await _execute("SELECT SUM(message_count) FROM user_stats WHERE chat_id=?", (chat_id,), fetch_one=True)
    active_users = await _execute("SELECT COUNT(*) FROM user_stats WHERE chat_id=?", (chat_id,), fetch_one=True)
    admin_count = await _execute("SELECT COUNT(*) FROM assistant_admins WHERE chat_id=?", (chat_id,), fetch_one=True)
    muted_users = await _execute("SELECT COUNT(*) FROM mutes WHERE chat_id=?", (chat_id,), fetch_one=True)
    return {
        "total_messages": total_messages[0] if total_messages and total_messages[0] else 0,
        "active_users": active_users[0] if active_users else 0,
        "admin_count": (admin_count[0] if admin_count else 0) + 1,
        "muted_users": muted_users[0] if muted_users else 0
    }

async def save_message_to_db(chat_id, message_id):
    await _execute("INSERT OR REPLACE INTO messages (chat_id, message_id, timestamp) VALUES (?, ?, ?)", 
                  (chat_id, message_id, int(time.time())))

async def get_recent_messages(chat_id, limit=100):
    rows = await _execute("SELECT message_id FROM messages WHERE chat_id=? ORDER BY timestamp DESC LIMIT ?", 
                          (chat_id, limit), fetch_all=True)
    return [row["message_id"] for row in rows] if rows else []

# ==================== تابع حذف دسته‌جمعی پیام‌ها (بهینه شده) ====================
async def delete_messages_from_db(chat_id, message_ids):
    """حذف دسته‌جمعی پیام‌ها از دیتابیس با استفاده از IN (بسیار سریع‌تر)"""
    if not message_ids:
        return
    # ساخت placeholder برای کوئری IN
    placeholders = ','.join('?' * len(message_ids))
    query = f"DELETE FROM messages WHERE chat_id=? AND message_id IN ({placeholders})"
    params = [chat_id] + message_ids
    await _execute(query, params)

async def set_group_rules(chat_id, rules_text):
    await _execute("INSERT OR REPLACE INTO group_rules_text (chat_id, rules_text) VALUES (?, ?)", (chat_id, rules_text))

async def get_group_rules(chat_id):
    row = await _execute("SELECT rules_text FROM group_rules_text WHERE chat_id=?", (chat_id,), fetch_one=True)
    return row["rules_text"] if row else "📝 هنوز قوانینی برای این گروه تنظیم نشده است."

async def set_bot_status(chat_id, status):
    await _execute("INSERT OR REPLACE INTO bot_status_chat (chat_id, status) VALUES (?, ?)", (chat_id, status))

async def get_bot_status(chat_id):
    row = await _execute("SELECT status FROM bot_status_chat WHERE chat_id=?", (chat_id,), fetch_one=True)
    return row["status"] if row else "on"

async def save_active_group(chat_id, group_info):
    await _execute("INSERT OR REPLACE INTO active_groups (chat_id, group_info) VALUES (?, ?)", (chat_id, group_info))

async def get_active_groups():
    rows = await _execute("SELECT chat_id, group_info FROM active_groups", fetch_all=True)
    return [(row["chat_id"], row["group_info"]) for row in rows] if rows else []

def random_tag_text():
    return random.choice(TAG_TEXTS)

def load_curse_words():
    return CURSE_WORDS

def load_challenges():
    return challenge_list

def load_hadiths():
    return hadiths

def load_memories():
    return memories

def load_stories():
    return stories

def _has_link(text: str) -> bool:
    if not text:
        return False
    pattern = r'(https?://|www\.|[a-zA-Z0-9]+\.(ir|com|net|org|tk|ga|ml|cf|gq|xyz|me))'
    return bool(re.search(pattern, text, re.IGNORECASE))

def check_rules(message: Message, chat_antilink_status, chat_rules, chat_id):
    violations = []
    if chat_antilink_status and message.text and _has_link(message.text):
        violations.append("لینک")
    if chat_rules.get("anti_mention") and message.text and "@" in message.text:
        violations.append("منشن")
    if chat_rules.get("anti_ad") and message.text:
        text_lower = message.text.lower()
        for pattern in AD_PATTERNS_COMPILED:
            if pattern.search(text_lower):
                violations.append("تبلیغ")
                break
    if chat_rules.get("anti_curse") and message.text:
        text_lower = message.text.lower()
        if any(curse in text_lower for curse in CURSE_WORDS_SET):
            violations.append("فحش")
    if chat_rules.get("anti_hung") and message.text:
        for pattern in HUNG_PATTERNS_COMPILED:
            if pattern.search(message.text):
                violations.append("کد هنگی")
                break
    if chat_rules.get("anti_emoji") and message.text:
        if not EMOJI_SET.isdisjoint(message.text):
            violations.append("ایموجی ممنوع")
    if message.text and chat_id in filtered_words_by_chat:
        text_lower = message.text.lower()
        for word in filtered_words_by_chat[chat_id]:
            if word in text_lower:
                violations.append("محتوای نامناسب")
                break
    if chat_rules.get("anti_edit") and getattr(message, 'is_edited', False):
        violations.append("ویرایش پیام")
    if chat_rules.get("gif") and getattr(message, 'is_gif', False):
        violations.append("گیف")
    return violations

async def send_channel_reminder():
    while True:
        await asyncio.sleep(12 * 3600)
        try:
            all_chats = await get_all_chats()
            reminder_text = f"📢 لطفاً از کانال ما دیدن کنید و عضو شوید ❤️\n{CHANNEL_LINK}"
            for chat_id in all_chats:
                try:
                    await bot.send_message(chat_id, reminder_text)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Failed to send reminder to {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Error in send_channel_reminder: {e}")

def build_stats_buttons(groups, users, total):
    return InlineBuilder()\
        .row(
            InlineBuilder().button_simple("1", "تعداد گروه‌ها"),
            InlineBuilder().button_simple("2", f"{groups}")
        )\
        .row(
            InlineBuilder().button_simple("1", "تعداد کاربران"),
            InlineBuilder().button_simple("2", f"{users}")
        )\
        .row(
            InlineBuilder().button_simple("1", "🗂️ کل چت‌ها"),
            InlineBuilder().button_simple("2", f"{total}")
        )\
        .build()

def build_admin_panel():
    return (
        ChatKeypadBuilder()
        .row(
            ChatKeypadBuilder().button(id="stats", text="📊 آمار ربات")
        )
        .row(
            ChatKeypadBuilder().button(id="broadcast_text", text="📝 ارسال همگانی"),
            ChatKeypadBuilder().button(id="broadcast_fwd", text="➡️ فوروارد همگانی")
        )
        .row(
            ChatKeypadBuilder().button(id="close_panel", text="❌ بستن پنل")
        )
        .build()
    )

async def ask_speaker_local(text):
    cleaned_text = text.strip().lower()
    for question in speaker_db.keys():
        if cleaned_text == question.lower():
            return random.choice(speaker_db[question])
    return None

async def process_message_with_rules(bot: Robot, message: Message, chat_id, chat_rules, antilink_status):
    if await is_group_creator(chat_id, message.sender_id):
        return False
    if await is_assistant_admin(chat_id, message.sender_id):
        return False
    bot_status_chat = await get_bot_status(chat_id)
    if bot_status_chat == "off":
        return False
    violations = check_rules(message, antilink_status, chat_rules, chat_id)
    if violations:
        texts = "، ".join(violations)
        try:
            await bot.send_message(
                chat_id,
                f"⛔ اخطار\n"
                f"> [کاربر]({message.sender_id}) عزیز\n"
                f"📌 دلیل: {texts}\n"
                f"⚠️ پیام شما به دلیل نقض قوانین حذف شد."
            )
            await bot.delete_message(chat_id, message.message_id)
        except Exception as e:
            logger.error(f"Error processing rule violation: {e}")
        return True
    return False

async def send_request(url, method="GET", **kwargs):
    timeout = kwargs.pop('timeout', 15)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method.upper() == "GET":
                response = await client.get(url, **kwargs)
            else:
                response = await client.post(url, **kwargs)
            return response.json()
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from {url}")
        return None
    except Exception as e:
        logger.error(f"Request error to {url}: {e}")
        return None

async def ask_ai_question(question: str):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{AI_API_URL}?text={question}",
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("result", "پاسخی دریافت نشد.")
            else:
                return f"خطا در ارتباط با هوش مصنوعی. کد خطا: {response.status_code}"
    except httpx.TimeoutException:
        return "⏳ زمان انتظار برای پاسخ هوش مصنوعی به پایان رسید."
    except Exception as e:
        logger.error(f"AI error: {e}")
        return f"خطا در دریافت پاسخ: {str(e)}"

def font(text_font: str):
    """تبدیل متن به فونت Full-width لاتین"""
    full_width = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    a_z = "abcdefghijklmnopqrstuvwxyz"
    trans = str.maketrans(a_z, full_width)
    return text_font.lower().translate(trans)

async def get_currency_prices():
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            requ = await cl.get("https://arzdigital.com/coins/", headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(requ.text, 'html.parser')
        j = {"bitcoin":"بیت کوین","ethereum":"اتریوم","xrp":"ریپل","tether":"تتر","bnb":"بایننس","solana":"سولانا","tron":"ترون"}
        m = {}
        pn = ["toman","dollar"]
        for key, item in j.items():
            for u in pn:
                span_tag = soup.find('span', class_=f'pulser-{u}-{key}').text
                if item not in m:
                    m[item] = {}
                m[item][u] = span_tag
        tt = "قیمت ۷ ارز دیجیتال به صورت لحظه‌ای 💱\n"
        for key, item in m.items():
            tt += f"\n - {key} -\n🇮🇷 تومان : {item['toman']}\n🇺🇸 دلار : {item['dollar']}\n"
        return tt
    except Exception as e:
        logger.error(f"Currency error: {e}")
        return "❌ خطا در دریافت اطلاعات ارز دیجیتال"

async def get_time_info():
    try:
        response = await send_request("https://api.parssource.ir/date/", timeout=10)
        dat = response['result']
        date = f"""تاریخ : {dat['jalaly']['date']} 📆
ساعت : {dat['jalaly']['time']} 🕥
روز هفته : {dat['jalaly']['dey_week']} 📆
ماه : {dat['jalaly']['mont']} 📅
حیوان سال : {dat['jalaly']['animal']} 🐾
فصل : {dat['jalaly']['season']} 🌳
مناسبت امروز : {dat['jalaly']['mon']} 🌇
مانده به عید : {str(dat['jalaly']['eid'])} 🌍
تاریخ میلادی : {dat['Gregorian']['date']} 📆
ساعت میلادی : {dat['Gregorian']['time']} 🕥"""
        return date
    except Exception as e:
        logger.error(f"Time info error: {e}")
        return "❌ خطا در دریافت اطلاعات زمان"

# ------------------- توابع ضد تبلیغ نام و عضویت -------------------
AD_NAME_PATTERNS = [
    r'\bبیو\b', r'\bچک\b', r'\bتبلیغ\b', r'\bلینک\b', r'\bسایت\b',
    r'\bفالو\b', r'\bکسب درآمد\b', r'\bآموزش\b', r'\bتضمینی\b',
    r'\bزیرمجموعه\b', r'\bهمکاری\b', r'\bاستخدام\b', r'\bاطلاعات\b'
]
AD_NAME_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in AD_NAME_PATTERNS]

def is_advertisement_name(name: str) -> bool:
    if not name:
        return False
    name_lower = name.lower()
    return any(pattern.search(name_lower) for pattern in AD_NAME_PATTERNS_COMPILED)

async def get_user_profile(user_id: str) -> dict:
    try:
        info = await bot.get_info(user_id)
        name = info.user.first_name if info and info.user else ""
        return {'full_name': name}
    except Exception as e:
        logger.error(f"Error getting user profile for {user_id}: {e}")
        return {}

async def _is_member(chat_id: str, user_id: str) -> bool:
    row = await _execute(
        "SELECT 1 FROM members WHERE chat_id=? AND user_id=?",
        (chat_id, user_id), fetch_one=True
    )
    return row is not None