# state.py
import aiosqlite
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from config import DB_PATH

# ==================== ساختارهای داده جدید ====================
admin_states = {}
broadcast_tasks = {}
group_rules = {}
bot_status = {}
active_groups = {}
user_warns: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
user_games: Dict[str, dict] = {}
user_cooldowns: Dict[str, Dict[str, float]] = defaultdict(dict)
daily_rewards: Dict[str, Dict[str, str]] = defaultdict(dict)
poll_votes: Dict[str, Dict[int, str]] = defaultdict(dict)
group_settings: Dict[str, dict] = defaultdict(dict)
message_history: Dict[str, List[int]] = defaultdict(list)
user_notes: Dict[str, Dict[int, List[dict]]] = defaultdict(lambda: defaultdict(list))
bot_giveaways: Dict[str, dict] = {}
user_badges: Dict[str, Dict[int, List[str]]] = defaultdict(lambda: defaultdict(list))
group_custom_commands: Dict[str, Dict[str, str]] = defaultdict(dict)
user_levels: Dict[str, Dict[int, dict]] = defaultdict(lambda: defaultdict(lambda: {"xp": 0, "level": 1}))
group_banlist: Dict[str, List[int]] = defaultdict(list)
group_filter_patterns: Dict[str, List[str]] = defaultdict(list)
user_reports: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
group_welcome_msgs: Dict[str, str] = {}
group_goodbye_msgs: Dict[str, str] = {}
group_captcha_settings: Dict[str, dict] = {}
user_captcha: Dict[str, Dict[int, dict]] = defaultdict(dict)
group_timers: Dict[str, Dict[str, int]] = defaultdict(dict)
quiz_questions: Dict[str, list] = {}
group_events: Dict[str, list] = defaultdict(list)
user_achievements: Dict[str, Dict[int, List[str]]] = defaultdict(lambda: defaultdict(list))
group_petitions: Dict[str, dict] = {}
bot_music_queue: Dict[str, list] = defaultdict(list)
user_favorites: Dict[str, Dict[int, List[int]]] = defaultdict(lambda: defaultdict(list))
group_custom_reactions: Dict[str, Dict[str, str]] = defaultdict(dict)
group_auto_responders: Dict[str, Dict[str, str]] = defaultdict(dict)
group_warnings_settings: Dict[str, dict] = defaultdict(lambda: {"max_warns": 3, "action": "mute", "duration": 3600})
group_invite_links: Dict[str, Dict[str, str]] = defaultdict(dict)
group_topics: Dict[str, dict] = {}
user_birthdays: Dict[str, Dict[int, str]] = defaultdict(dict)
group_reminders: Dict[str, List[dict]] = defaultdict(list)
group_blacklist_words: Dict[str, List[str]] = defaultdict(list)
group_whitelist_links: Dict[str, List[str]] = defaultdict(list)
group_log_channels: Dict[str, str] = {}
group_auto_roles: Dict[str, dict] = defaultdict(dict)
group_voice_chat: Dict[str, dict] = {}
group_bot_protection: Dict[str, bool] = defaultdict(bool)

# ==================== دیتابیس‌های جدید (غیرهمزمان) ====================
async def init_db_advanced():
    """ایجاد جداول پیشرفته با aiosqlite (فقط یک بار در ابتدا)"""
    async with aiosqlite.connect(DB_PATH) as db:
        # کاربران و سطوح
        await db.execute("""CREATE TABLE IF NOT EXISTS user_levels (
            chat_id TEXT, user_id TEXT, xp INTEGER, level INTEGER, 
            last_xp_time INTEGER, PRIMARY KEY (chat_id, user_id))""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS user_badges (
            user_id TEXT, chat_id TEXT, badge TEXT, earned_time INTEGER, 
            PRIMARY KEY (user_id, chat_id, badge))""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS custom_commands (
            chat_id TEXT, command TEXT, response TEXT, created_by TEXT, 
            created_time INTEGER, PRIMARY KEY (chat_id, command))""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS group_warns (
            chat_id TEXT, user_id TEXT, warn_count INTEGER, 
            last_warn_time INTEGER, PRIMARY KEY (chat_id, user_id))""")
        
        # دعوت‌نامه‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_invites (
            chat_id TEXT, link TEXT, creator_id TEXT, created_time INTEGER, 
            uses INTEGER, PRIMARY KEY (chat_id, link))""")
        
        # موضوعات گروه
        await db.execute("""CREATE TABLE IF NOT EXISTS group_topics (
            chat_id TEXT, topic_id TEXT, topic_name TEXT, creator_id TEXT, 
            PRIMARY KEY (chat_id, topic_id))""")
        
        # تولدها
        await db.execute("""CREATE TABLE IF NOT EXISTS user_birthdays (
            chat_id TEXT, user_id TEXT, birthday TEXT, 
            PRIMARY KEY (chat_id, user_id))""")
        
        # یادآوری‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_reminders (
            chat_id TEXT, reminder_id TEXT, user_id TEXT, 
            reminder_text TEXT, remind_time INTEGER, PRIMARY KEY (chat_id, reminder_id))""")
        
        # لیست سیاه کلمات
        await db.execute("""CREATE TABLE IF NOT EXISTS group_blacklist (
            chat_id TEXT, word TEXT, added_by TEXT, added_time INTEGER, 
            PRIMARY KEY (chat_id, word))""")
        
        # لیست سفید لینک‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_whitelist (
            chat_id TEXT, link_pattern TEXT, added_by TEXT, 
            PRIMARY KEY (chat_id, link_pattern))""")
        
        # کانال‌های لاگ
        await db.execute("""CREATE TABLE IF NOT EXISTS group_logs (
            chat_id TEXT, log_channel TEXT, settings TEXT, 
            PRIMARY KEY (chat_id, log_channel))""")
        
        # نقش‌های خودکار
        await db.execute("""CREATE TABLE IF NOT EXISTS group_auto_roles (
            chat_id TEXT, role_name TEXT, role_id TEXT, 
            min_level INTEGER, PRIMARY KEY (chat_id, role_name))""")
        
        # یادداشت‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS user_notes (
            chat_id TEXT, user_id TEXT, note_id TEXT, note_text TEXT, 
            created_by TEXT, created_time INTEGER, PRIMARY KEY (chat_id, user_id, note_id))""")
        
        # قرعه‌کشی‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_giveaways (
            chat_id TEXT, giveaway_id TEXT, prize TEXT, winner_count INTEGER, 
            end_time INTEGER, created_by TEXT, participants TEXT, 
            PRIMARY KEY (chat_id, giveaway_id))""")
        
        # مسابقات
        await db.execute("""CREATE TABLE IF NOT EXISTS group_quiz (
            chat_id TEXT, quiz_id TEXT, question TEXT, options TEXT, 
            correct_answer INTEGER, created_by TEXT, PRIMARY KEY (chat_id, quiz_id))""")
        
        # رویدادها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_events (
            chat_id TEXT, event_id TEXT, event_name TEXT, event_time INTEGER, 
            event_description TEXT, created_by TEXT, participants TEXT, 
            PRIMARY KEY (chat_id, event_id))""")
        
        # دستاوردها
        await db.execute("""CREATE TABLE IF NOT EXISTS user_achievements (
            user_id TEXT, chat_id TEXT, achievement TEXT, earned_time INTEGER, 
            PRIMARY KEY (user_id, chat_id, achievement))""")
        
        # الگوهای فیلتر
        await db.execute("""CREATE TABLE IF NOT EXISTS group_filter_patterns (
            chat_id TEXT, pattern TEXT, added_by TEXT, severity INTEGER, 
            PRIMARY KEY (chat_id, pattern))""")
        
        # پاسخگوی خودکار
        await db.execute("""CREATE TABLE IF NOT EXISTS group_auto_responders (
            chat_id TEXT, trigger TEXT, response TEXT, mode TEXT, 
            created_by TEXT, PRIMARY KEY (chat_id, trigger))""")
        
        # خنک‌سازی دستورات
        await db.execute("""CREATE TABLE IF NOT EXISTS user_cooldowns (
            chat_id TEXT, user_id TEXT, command TEXT, last_use INTEGER, 
            PRIMARY KEY (chat_id, user_id, command))""")
        
        # تنظیمات اخطار
        await db.execute("""CREATE TABLE IF NOT EXISTS group_warnings_settings (
            chat_id TEXT PRIMARY KEY, max_warns INTEGER, action TEXT, duration INTEGER)""")
        
        # پیام خوش‌آمد
        await db.execute("""CREATE TABLE IF NOT EXISTS group_welcome (
            chat_id TEXT PRIMARY KEY, welcome_text TEXT, media_id TEXT, is_active INTEGER)""")
        
        # پیام خداحافظ
        await db.execute("""CREATE TABLE IF NOT EXISTS group_goodbye (
            chat_id TEXT PRIMARY KEY, goodbye_text TEXT, media_id TEXT, is_active INTEGER)""")
        
        # تنظیمات کپچا
        await db.execute("""CREATE TABLE IF NOT EXISTS group_captcha (
            chat_id TEXT PRIMARY KEY, is_active INTEGER, difficulty TEXT, kick_time INTEGER)""")
        
        # تایمرها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_timers (
            chat_id TEXT, timer_name TEXT, timer_time INTEGER, repeat INTEGER, 
            action TEXT, created_by TEXT, PRIMARY KEY (chat_id, timer_name))""")
        
        # صف موسیقی
        await db.execute("""CREATE TABLE IF NOT EXISTS bot_music_queue (
            chat_id TEXT, song_id TEXT, title TEXT, url TEXT, added_by TEXT, 
            added_time INTEGER, PRIMARY KEY (chat_id, song_id))""")
        
        # علاقه‌مندی‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS user_favorites (
            user_id TEXT, chat_id TEXT, message_id INTEGER, saved_time INTEGER, 
            PRIMARY KEY (user_id, chat_id, message_id))""")
        
        # واکنش‌های سفارشی
        await db.execute("""CREATE TABLE IF NOT EXISTS group_custom_reactions (
            chat_id TEXT, trigger TEXT, reaction TEXT, mode TEXT, 
            created_by TEXT, PRIMARY KEY (chat_id, trigger))""")
        
        # طومارها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_petitions (
            chat_id TEXT, petition_id TEXT, title TEXT, description TEXT, 
            target_votes INTEGER, current_votes INTEGER, created_by TEXT, 
            end_time INTEGER, PRIMARY KEY (chat_id, petition_id))""")
        
        # امضاهای طومار
        await db.execute("""CREATE TABLE IF NOT EXISTS petition_signatures (
            chat_id TEXT, petition_id TEXT, user_id TEXT, signed_time INTEGER, 
            PRIMARY KEY (chat_id, petition_id, user_id))""")
        
        # پاداش روزانه
        await db.execute("""CREATE TABLE IF NOT EXISTS daily_rewards (
            user_id TEXT, chat_id TEXT, last_claim_date TEXT, streak INTEGER, 
            PRIMARY KEY (user_id, chat_id))""")
        
        # چت صوتی
        await db.execute("""CREATE TABLE IF NOT EXISTS group_voice_chat (
            chat_id TEXT PRIMARY KEY, is_active INTEGER, title TEXT, 
            schedule_time INTEGER, created_by TEXT)""")
        
        # محافظت از بات
        await db.execute("""CREATE TABLE IF NOT EXISTS group_bot_protection (
            chat_id TEXT PRIMARY KEY, is_active INTEGER, kick_new_bots INTEGER, 
            ban_known_bots INTEGER)""")
        
        # تگ‌ها
        await db.execute("""CREATE TABLE IF NOT EXISTS group_tags (
            chat_id TEXT, tag_name TEXT, user_ids TEXT, created_by TEXT, 
            created_time INTEGER, PRIMARY KEY (chat_id, tag_name))""")
        
        # نظرسنجی پیشرفته
        await db.execute("""CREATE TABLE IF NOT EXISTS group_polls_advanced (
            chat_id TEXT, poll_id TEXT, question TEXT, options TEXT, 
            is_anonymous INTEGER, multiple_choices INTEGER, created_by TEXT, 
            end_time INTEGER, votes TEXT, PRIMARY KEY (chat_id, poll_id))""")
        
        # لینک‌های گروه
        await db.execute("""CREATE TABLE IF NOT EXISTS group_links (
            chat_id TEXT, link_type TEXT, link_url TEXT, title TEXT, 
            added_by TEXT, added_time INTEGER, PRIMARY KEY (chat_id, link_url))""")
        
        # نشست‌های کپچا
        await db.execute("""CREATE TABLE IF NOT EXISTS captcha_sessions (
            chat_id TEXT,
            user_id TEXT,
            question TEXT,
            answer INTEGER,
            attempts INTEGER DEFAULT 1,
            expires INTEGER,
            message_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )""")
        
        await db.commit()