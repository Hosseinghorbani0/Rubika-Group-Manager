# handler.py
import asyncio
import random
import logging
from datetime import datetime
from typing import Optional
import json
import time

from rubka.asynco import Robot, Message
from rubka.button import InlineBuilder, ChatKeypadBuilder
from rubka import filters

from config import ADMIN_CHAT_ID, CHANNEL_CREATOR, CHANNEL_LINK, AI_API_URL, bot
from state import user_games, admin_states
from library import riddles

from database import (
    add_user_xp, get_user_level_info, get_user_badges,
    get_group_leaderboard, get_custom_command, list_custom_commands,
    _execute  # اضافه شد
)

from games import (
    start_math_game, start_word_game, start_guess_number_game, check_game_answer
)

from fun import (
    get_random_fortune, get_random_joke, get_random_fact, get_random_movie,
    get_english_tip, get_health_tip, get_random_prayer, get_random_islamic_rule,
    get_random_philosophy, get_riddle_answer, get_hafez_fal,
    get_personality_test, get_birthday_horoscope, calculate_age,
    get_qibla_direction, get_ramadan_info
)

from utils import (
    is_group_creator, is_assistant_admin, get_group_creator, get_group_rules, set_group_rules,
    load_challenges, load_hadiths, load_memories, load_stories,
    get_time_info, font, get_currency_prices, send_request, ask_ai_question,
    get_learning, save_learning, delete_learning, list_learnings,
    get_speaker_status, set_speaker_status, set_bot_status, get_bot_status,
    add_filtered_word, set_antilink_status, set_rule_status, get_rule_status, invalidate_rules_cache,
    get_antilink_status, rules_fa, speaker_db, ask_speaker_local,
    get_counts, get_total_count, get_all_chats,
    build_stats_buttons, build_admin_panel,
    is_first_message, save_chat_id,
    init_rules, save_active_group,
    get_user_stats, get_group_stats
)  # _execute_db_query حذف شد

logger = logging.getLogger(__name__)

last_riddles: dict = {}

# ======================== تابع پردازش دستورات عمومی گروه ========================
async def process_group_commands(bot: Robot, message: Message, chat_id: str, user_id: str, text: str) -> Optional[bool]:
    """
    دستورات عمومی، سرگرمی، ابزاری و مالک گروه که خارج از بلوک ادمین هستند.
    اگر دستوری شناسایی و پردازش شد، True برمی‌گرداند.
    """
    # سطح
    if text == "سطح":
        level_info = await get_user_level_info(chat_id, user_id)
        progress_bar = "▓" * int(level_info['progress'] / 10) + "░" * (10 - int(level_info['progress'] / 10))
        await message.reply(
            f"⭐ **اطلاعات سطح شما** ⭐\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 کاربر: [کاربر]({user_id})\n"
            f"🎚️ سطح: **{level_info['level']}**\n"
            f"📊 تجربه: {level_info['xp']}/{level_info['xp_needed']}\n"
            f"📈 پیشرفت: {progress_bar} {level_info['progress']}%\n"
            f"🎯 تجربه مورد نیاز تا سطح بعد: {level_info['xp_remaining']}"
        )
        return True

    # نشان‌ها
    elif text == "نشان‌ها":
        badges = await get_user_badges(user_id, chat_id)
        if badges:
            badge_icons = {
                "group_founder": "👑 بنیانگذار",
                "group_admin": "🛡️ مدیر",
                "level_5": "🥉 برنزی",
                "level_10": "🥈 نقره‌ای",
                "level_20": "🥇 طلایی",
                "level_50": "💎 الماسی"
            }
            msg = "🏅 **نشان‌های شما:**\n\n"
            for badge, time_ in badges:
                badge_name = badge_icons.get(badge, badge)
                date = datetime.fromtimestamp(time_).strftime("%Y/%m/%d")
                msg += f"• {badge_name} - دریافت در {date}\n"
            await message.reply(msg)
        else:
            await message.reply("📭 شما هنوز هیچ نشانی دریافت نکرده‌اید!")
        return True

    # لیست برترین‌ها
    elif text == "لیست برترین‌ها":
        leaderboard = await get_group_leaderboard(chat_id, 10)
        if leaderboard:
            msg = "🏆 **برترین‌های گروه** 🏆\n━━━━━━━━━━━━━━━\n"
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for i, (uid, level, xp) in enumerate(leaderboard):
                medal = medals[i] if i < len(medals) else "🔹"
                msg += f"{medal} [کاربر]({uid}) - سطح {level} ({xp} XP)\n"
            await message.reply(msg)
        else:
            await message.reply("📭 هنوز کاربری در این گروه فعالیت نکرده است!")
        return True

    # بازی ریاضی
    elif text == "بازی ریاضی":
        game = await start_math_game(chat_id, user_id)
        await message.reply(game["question"])
        return True

    # بازی کلمات
    elif text == "بازی کلمات":
        game = await start_word_game(chat_id, user_id)
        await message.reply(game["question"])
        return True

    # بازی حدس عدد
    elif text == "بازی حدس عدد":
        game = await start_guess_number_game(chat_id, user_id)
        await message.reply(game["question"])
        return True

    # جواب بازی
    elif text.startswith("جواب "):
        answer = text[5:].strip()
        active_games = [
            (gid, game) for gid, game in user_games.items()
            if game["chat_id"] == chat_id and game["user_id"] == user_id
        ]
        if not active_games:
            await message.reply("❌ شما بازی فعالی ندارید!")
            return True
        game_id, _ = max(active_games, key=lambda x: x[1]["start_time"])
        success, result = await check_game_answer(game_id, user_id, answer)
        await message.reply(result)
        return True

    # فال حافظ
    elif text == "فال حافظ":
        fal = await get_hafez_fal()
        if fal:
            await message.reply(f"🍃 **فال حافظ** 🍃\n━━━━━━━━━━━━━━━\n{fal}\n━━━━━━━━━━━━━━━\n✨ الهی به امید تو...")
        else:
            await message.reply("⚠️ در حال حاضر فال حافظ در دسترس نیست.")
        return True

    # معما
    elif text == "معما":
        if not riddles:
            await message.reply("⚠️ معمایی برای نمایش وجود ندارد.")
            return True
        riddle = random.choice(riddles)
        last_riddles[chat_id] = riddle["question"]
        riddle_text = f"🧩 **معما:**\n{riddle['question']}\n\n📝 برای دیدن جواب بنویس: جواب معما"
        await message.reply(riddle_text)
        return True

    # جواب معما
    elif text == "جواب معما":
        if chat_id in last_riddles:
            question = last_riddles[chat_id]
            answer = await get_riddle_answer(question)
            if answer:
                await message.reply(answer)
            else:
                await message.reply("❌ جوابی برای این معما یافت نشد.")
        else:
            await message.reply("❌ معمایی برای جواب دادن وجود ندارد! ابتدا دستور «معما» را بزنید.")
        return True

    # فال روز
    elif text == "فال روز":
        fortune = await get_random_fortune()
        await message.reply(f"🔮 **فال روزانه شما** 🔮\n━━━━━━━━━━━━━━━\n{fortune}" if fortune else "⚠️ فال روز در دسترس نیست.")
        return True

    # لطیفه
    elif text == "لطیفه":
        joke = await get_random_joke()
        await message.reply(f"😂 **لطیفه:**\n{joke}" if joke else "⚠️ لطیفه‌ای یافت نشد.")
        return True

    # حقیقت جالب
    elif text == "حقیقت جالب":
        fact = await get_random_fact()
        await message.reply(f"🤔 **آیا می‌دانستید؟**\n{fact}" if fact else "⚠️ حقیقت جالبی پیدا نشد.")
        return True

    # پیشنهاد فیلم
    elif text == "پیشنهاد فیلم":
        movie = await get_random_movie()
        await message.reply(movie if movie else "⚠️ پیشنهادی موجود نیست.")
        return True

    # نکته انگلیسی
    elif text == "نکته انگلیسی":
        tip = await get_english_tip()
        await message.reply(tip if tip else "⚠️ نکته انگلیسی موجود نیست.")
        return True

    # سلامتی
    elif text == "سلامتی":
        tip = await get_health_tip()
        await message.reply(f"💚 **نکته سلامتی:**\n{tip}" if tip else "⚠️ نکته سلامتی موجود نیست.")
        return True

    # دعا
    elif text == "دعا":
        prayer = await get_random_prayer()
        await message.reply(prayer if prayer else "⚠️ دعایی یافت نشد.")
        return True

    # حکم شرعی
    elif text == "حکم شرعی":
        rule = await get_random_islamic_rule()
        await message.reply(rule if rule else "⚠️ حکم شرعی یافت نشد.")
        return True

    # جمله فلسفی
    elif text == "جمله فلسفی":
        quote = await get_random_philosophy()
        await message.reply(f"💭 **جمله فلسفی:**\n{quote}" if quote else "⚠️ جمله فلسفی موجود نیست.")
        return True

    # قبله
    elif text == "قبله":
        qibla = await get_qibla_direction()
        await message.reply(qibla)
        return True

    # رمضان
    elif text == "رمضان":
        ramadan = await get_ramadan_info()
        await message.reply(ramadan)
        return True

    # تست شخصیت
    elif text.startswith("تست شخصیت "):
        parts = text.split(' ', 2)
        if len(parts) >= 3:
            rest = parts[2].strip()
            sub_parts = rest.split(' ', 1)
            if len(sub_parts) == 2:
                category = sub_parts[0]
                choice = sub_parts[1]
            else:
                await message.reply("❌ فرمت صحیح: تست شخصیت [دسته] [گزینه]\nمثال: تست شخصیت رنگ قرمز")
                return True
            result = await get_personality_test(category, choice)
            if result:
                await message.reply(result)
            else:
                await message.reply("❌ تست شخصیت یافت نشد!\nمثال: تست شخصیت رنگ قرمز")
        else:
            await message.reply("❌ فرمت صحیح: تست شخصیت [دسته] [گزینه]\nمثال: تست شخصیت رنگ قرمز")
        return True

    # طالع بینی
    elif text.startswith("طالع بینی "):
        month = text.split(' ', 2)[-1].strip() if len(text.split(' ', 2)) > 2 else None
        if not month:
            await message.reply("❌ ماه وارد شده صحیح نیست!\nمثال: طالع بینی فروردین")
            return True
        horoscope = await get_birthday_horoscope(month)
        if horoscope:
            await message.reply(horoscope)
        else:
            await message.reply("❌ ماه وارد شده صحیح نیست!\nمثال: طالع بینی فروردین")
        return True

    # سن
    elif text.startswith("سن "):
        date_str = text[4:].strip()
        try:
            parts = date_str.split("/")
            if len(parts) == 3:
                age_info = await calculate_age(parts[0], parts[1], parts[2])
                if age_info:
                    await message.reply(
                        f"🎂 **اطلاعات سن شما**\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"📅 سن: **{age_info['age']}** سال\n"
                        f"🎈 مانده به تولد بعدی: **{age_info['days_to_birthday']}** روز\n"
                        f"📆 تاریخ تولد بعدی: {age_info['next_birthday']}"
                    )
                else:
                    await message.reply("❌ تاریخ وارد شده نامعتبر است!")
            else:
                await message.reply("❌ فرمت صحیح: سن 1370/01/01")
        except:
            await message.reply("❌ فرمت صحیح: سن 1370/01/01")
        return True

    # احادیث
    elif text == "احادیث":
        all_hadiths = load_hadiths()
        if not all_hadiths:
            await message.reply("⚠️ حدیثی موجود نیست.")
        else:
            random_hadith = random.choice(all_hadiths)
            await message.reply(f"📖 **حدیث تصادفی:**\n\n{random_hadith}\n\n➡️ برای حدیث دیگر: حدیث")
        return True

    # خاطرات
    elif text == "خاطرات":
        all_memories = load_memories()
        if not all_memories:
            await message.reply("⚠️ خاطره‌ای موجود نیست.")
        else:
            random_memory = random.choice(all_memories)
            await message.reply(f"📓 **خاطره:**\n\n{random_memory}")
        return True

    # داستان‌ها
    elif text == "داستان‌ها":
        all_stories = load_stories()
        if not all_stories:
            await message.reply("⚠️ داستانی موجود نیست.")
        else:
            random_story = random.choice(all_stories)
            await message.reply(f"📚 **داستان کوتاه:**\n\n{random_story}")
        return True

    # چالش‌ها
    elif text == "چالش‌ها":
        challenges = load_challenges()
        if not challenges:
            await message.reply("⚠️ چالشی موجود نیست.")
        else:
            random_challenge = random.choice(challenges)
            await message.reply(f"🎯 **چالش امروز:**\n\n{random_challenge}")
        return True

    # هوش مصنوعی
    from ai_assistant import process_ai_command
    if await process_ai_command(message, chat_id, text):
        return True

    # دستورات سفارشی با !
    if text.startswith("!"):
        cmd_response = await get_custom_command(chat_id, text)
        if cmd_response:
            await message.reply(cmd_response)
            return True

    # راهنما
        # راهنما (نسخه خلاصه با لینک به کانال)
    if text in ["دستورات", "راهنما", "help"]:
        help_message = (
            "🤖 **راهنمای سریع ربات سخنگو** 🤖\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 **دستورات پایه:**\n"
            "/start - شروع و آمار ربات\n"
            "فعال - ثبت به عنوان مالک گروه\n"
            "وضعیت - وضعیت خلاصه قوانین\n"
            "وضعیت کامل - نمایش تمام قوانین\n"
            "قوانین - نمایش متن قوانین گروه\n\n"
            
            "⚙️ **مدیریت سریع (فقط ادمین):**\n"
            "سکوت [دقیقه/دائمی] (ریپلای) - سکوت کاربر\n"
            "بن / آن بن (ریپلای) - اخراج / لغو اخراج\n"
            "اخطار / کاهش اخطار (ریپلای)\n"
            "حذف [تعداد] - پاکسازی پیام‌های اخیر\n"
            "تگ [همه/ادمین/فعال] - منشن گروهی\n"
            "کپچا روشن/خاموش - فعال‌سازی تأیید امنیتی\n\n"
            
            "🎮 **سرگرمی:**\n"
            "لطیفه، فال حافظ، معما، بازی ریاضی، +سوال\n\n"
            
            "📚 **آموزش به ربات (فقط سازنده):**\n"
            "یادگیری - [سوال] - [پاسخ]\n"
            "لیست یادگیری‌ها\n\n"
            
            "🔐 **کپچا (تأیید امنیتی):**\n"
            "کاربران جدید تا حل کپچا نمی‌توانند پیام بفرستند.\n"
            "پس از ۶ تلاش ناموفق، برای همیشه سکوت می‌شوند.\n"
            "ادمین می‌تواند با دستور «معاف-<user_id>» سکوت را بردارد.\n\n"
            
            "🔗 **سایر:**\n"
            "سازنده - اطلاعات سازنده\n"
            "ربات روشن/خاموش (فقط سازنده)\n\n"
            
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📢 **برای مشاهده ۹۹ دستور دیگر (بازی‌ها، ابزارها، مدیریت پیشرفته) به کانال ما مراجعه کنید:**\n"
            "👉 @bot_nora 👈\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 سازنده ربات: @nicot_com"
        )
        if len(help_message) > 4096:
            parts = [help_message[i:i+4096] for i in range(0, len(help_message), 4096)]
            for part in parts:
                await message.reply(part)
        else:
            await message.reply(help_message)
        return True

    # ربات روشن/خاموش (فقط سازنده)
    if text in ["ربات روشن", "ربات خاموش"]:
        if await is_group_creator(chat_id, user_id):
            status = "on" if text == "ربات روشن" else "off"
            await set_bot_status(chat_id, status)
            await message.reply(f"✅ ربات در این گروه {'روشن' if status == 'on' else 'خاموش'} شد.")
        else:
            await message.reply("❌ فقط سازنده گروه می‌تواند ربات را روشن/خاموش کند.")
        return True

    # نمایش قوانین گروه
    if text == "قوانین":
        rules_text = await get_group_rules(chat_id)
        await message.reply(f"📜 **قوانین گروه**\n\n{rules_text}")
        return True

    # تنظیم قوانین گروه (فقط ادمین)
    if text.startswith("تنظیم قوانین "):
        if await is_assistant_admin(chat_id, user_id):
            rules_text = text.replace("تنظیم قوانین ", "").strip()
            if rules_text:
                await set_group_rules(chat_id, rules_text)
                await message.reply("✅ قوانین گروه با موفقیت تنظیم شد.")
            else:
                await message.reply("❌ لطفاً متن قوانین را وارد کنید.")
        else:
            await message.reply("❌ فقط ادمین‌ها می‌توانند قوانین را تنظیم کنند.")
        return True

    # چالش، حدیث، خاطره، داستان
    if text in ["چالش", "حدیث", "خاطره", "داستان"]:
        if text == "چالش":
            challenges = load_challenges()
            if not challenges:
                await message.reply("❌ لیست چالش‌ها خالی است.")
            else:
                challenge = random.choice(challenges)
                await message.reply(f"⌯ #CHALECH\n\n🌼«{challenge}»")
            return True
        elif text == "حدیث":
            hadiths = load_hadiths()
            if not hadiths:
                await message.reply("❌ لیست احادیث خالی است.")
            else:
                hadith = random.choice(hadiths)
                await message.reply(f"⌯ #HADITH\n\n🌼«{hadith}»")
            return True
        elif text == "خاطره":
            memories = load_memories()
            if not memories:
                await message.reply("❌ لیست خاطرات خالی است.")
            else:
                memory = random.choice(memories)
                await message.reply(f"⌯ #MEMORY\n\n🌼«{memory}»")
            return True
        elif text == "داستان":
            stories = load_stories()
            if not stories:
                await message.reply("❌ لیست داستان‌ها خالی است.")
            else:
                story = random.choice(stories)
                await message.reply(f"⌯ #STORY\n\n🌼«{story}»")
            return True

    # ساعت
    if text == "ساعت":
        time_info = await get_time_info()
        await message.reply(time_info)
        return True

    # فونت
    if text.startswith("فونت "):
        text_to_font = text.replace("فونت ", "").strip()
        if text_to_font:
            font_text = font(text_to_font)
            await message.reply(f"🔤 **فونت زیبا:**\n\n{font_text}")
        else:
            await message.reply("❌ لطفاً متنی برای تبدیل به فونت وارد کنید.")
        return True

    # ارزدیجیتال
    if text == "ارزدیجیتال":
        currency_prices = await get_currency_prices()
        await message.reply(currency_prices)
        return True

    # سرچ در مایکت
    if text.startswith("سرچ "):
        app_name = text.replace("سرچ ", "").strip()
        if app_name:
            try:
                data = await send_request(f"https://hakhamanesh-bot.ir/api/myket/?text={app_name}&lang=fa&count=3")
                rapp = data.get("data", [])
                if not isinstance(rapp, list) or len(rapp) == 0:
                    await message.reply("❌ نتیجه‌ای یافت نشد.")
                    return True
                text_send = f"🔍 **جستجو برای: {app_name}**\n━━━━━━━━━━━━━━━\n"
                for i, app in enumerate(rapp[:3], 1):
                    text_send += (
                        f"\n**🔹 نتیجه {i}:** \n"
                        f"📱 نام: {app.get('title', 'نامعلوم')}\n"
                        f"🖼 عکس: {app.get('photo', '')}\n"
                        f"⬇️ لینک مستقیم: {app.get('download', '')}\n"
                        f"🔗 لینک مایکت: {app.get('link', '')}\n"
                    )
                await message.reply(text_send)
            except Exception as e:
                await message.reply(f"❌ خطا در جستجو: {str(e)}")
        else:
            await message.reply("❌ لطفاً نام برنامه را وارد کنید.")
        return True

    # تاس
    if text.startswith("تاس "):
        try:
            parts = text.split()
            if len(parts) == 2:
                user_choice = parts[1].lower()
                if user_choice not in ["زوج", "فرد"]:
                    await message.reply("❌ لطفاً «زوج» یا «فرد» را انتخاب کنید.")
                    return True
                dice_result = random.randint(1, 6)
                is_even = dice_result % 2 == 0
                result_text = "زوج" if is_even else "فرد"
                if (user_choice == "زوج" and is_even) or (user_choice == "فرد" and not is_even):
                    await message.reply(f"🎲 تاس افتاد: {dice_result} ({result_text})\n✅ درست حدس زدی! آفرین! 🎉")
                    await add_user_xp(chat_id, user_id, 5)
                else:
                    await message.reply(f"🎲 تاس افتاد: {dice_result} ({result_text})\n❌ اشتباه حدس زدی! دفعه بعد شانس با توئه! 😉")
            else:
                await message.reply("❌ فرمت: تاس زوج/فرد")
        except Exception as e:
            await message.reply(f"❌ خطا در بازی تاس: {str(e)}")
        return True

    # سازنده ربات
    if text in ["سازنده", "مالک ربات", "خالق"]:
        await message.reply(f"👨‍💻 سازنده ربات: {CHANNEL_CREATOR}\n📢 کانال: {CHANNEL_LINK}")
        return True

    # دستورات فقط برای سازنده گروه (مدیریت قوانین و یادگیری)
    if await is_group_creator(chat_id, user_id):
        # ضد لینک
        if text == "ضد لینک روشن":
            await set_antilink_status(chat_id, "on")
            await message.reply("✅ ضد لینک روشن شد.")
            return True
        elif text == "ضد لینک خاموش":
            await set_antilink_status(chat_id, "off")
            await message.reply("❌ ضد لینک خاموش شد.")
            return True
        # سخنگو
        elif text == "سخنگو روشن":
            await set_speaker_status(chat_id, "on")
            await message.reply("✅ سخنگو روشن شد.")
            return True
        elif text == "سخنگو خاموش":
            await set_speaker_status(chat_id, "off")
            await message.reply("❌ سخنگو خاموش شد.")
            return True
        # ضد تبلیغ
        elif text == "ضد تبلیغ روشن":
            await set_rule_status(chat_id, "anti_ad", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد تبلیغ روشن شد.")
            return True
        elif text == "ضد تبلیغ خاموش":
            await set_rule_status(chat_id, "anti_ad", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد تبلیغ خاموش شد.")
            return True
        # ضد فحش
        elif text == "ضد فحش روشن":
            await set_rule_status(chat_id, "anti_curse", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد فحش روشن شد.")
            return True
        elif text == "ضد فحش خاموش":
            await set_rule_status(chat_id, "anti_curse", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد فحش خاموش شد.")
            return True
        # ضد هنگی
        elif text == "ضد هنگی روشن":
            await set_rule_status(chat_id, "anti_hung", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد هنگی روشن شد.")
            return True
        elif text == "ضد هنگی خاموش":
            await set_rule_status(chat_id, "anti_hung", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد هنگی خاموش شد.")
            return True
        # ضد ایموجی
        elif text == "ضد ایموجی روشن":
            await set_rule_status(chat_id, "anti_emoji", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد ایموجی روشن شد.")
            return True
        elif text == "ضد ایموجی خاموش":
            await set_rule_status(chat_id, "anti_emoji", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد ایموجی خاموش شد.")
            return True
        # ضد ویرایش
        elif text == "ضد ویرایش روشن":
            await set_rule_status(chat_id, "anti_edit", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد ویرایش روشن شد.")
            return True
        elif text == "ضد ویرایش خاموش":
            await set_rule_status(chat_id, "anti_edit", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد ویرایش خاموش شد.")
            return True
        # ضد منشن
        elif text == "ضد منشن روشن":
            await set_rule_status(chat_id, "anti_mention", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد منشن روشن شد.")
            return True
        elif text == "ضد منشن خاموش":
            await set_rule_status(chat_id, "anti_mention", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد منشن خاموش شد.")
            return True
        # ضد گیف
        elif text == "ضد گیف روشن":
            await set_rule_status(chat_id, "gif", "on")
            await invalidate_rules_cache(chat_id)
            await message.reply("✅ ضد گیف روشن شد.")
            return True
        elif text == "ضد گیف خاموش":
            await set_rule_status(chat_id, "gif", "off")
            await invalidate_rules_cache(chat_id)
            await message.reply("❌ ضد گیف خاموش شد.")
            return True
        # فیلتر کلمه
        elif text.startswith("فیلتر "):
            word = text.replace("فیلتر ", "").strip()
            if word:
                await add_filtered_word(chat_id, word)
                await message.reply(f"✅ کلمه '{word}' به لیست فیلتر اضافه شد.")
            else:
                await message.reply("❌ لطفاً یک کلمه برای فیلتر کردن وارد کنید.")
            return True
        # یادگیری
        if text.startswith("یادگیری -"):
            parts = text.split("-", 2)
            if len(parts) == 3:
                _, question, answer = parts
                await save_learning(chat_id, question, answer)
                await message.reply(f"🤖 یاد گرفتم که وقتی گفتن '{question.strip()}' بگم '{answer.strip()}'")
            else:
                await message.reply("❌ فرمت درست نیست!\nمثال: یادگیری - سلام - خوبی")
            return True
        if text.startswith("حذف یادگیری -"):
            parts = text.split("-", 1)
            if len(parts) == 2:
                _, question = parts
                await delete_learning(chat_id, question)
                await message.reply(f"🗑 یادگیری '{question.strip()}' حذف شد.")
            else:
                await message.reply("❌ فرمت درست نیست!\nمثال: حذف یادگیری - سلام")
            return True
        if text == "لیست یادگیری‌ها":
            data = await list_learnings(chat_id)
            if not data:
                await message.reply("🤖 هنوز چیزی یاد نگرفتم!")
            else:
                msg = "📚 **یادگیری‌های فعلی:**\n\n"
                for q, a in data:
                    msg += f"• {q} → {a}\n"
                if len(msg) > 4096:
                    parts = [msg[i:i+4096] for i in range(0, len(msg), 4096)]
                    for part in parts:
                        await message.reply(part)
                else:
                    await message.reply(msg)
            return True
        # وضعیت گروه
        if text == "وضعیت گروه":
            creator = await get_group_creator(chat_id)
            if creator:
                creator_name = f"[سازنده]({creator})"
            else:
                creator_name = "⚠️ هنوز تنظیم نشده"
            speaker_status_str = "🟢 روشن" if await get_speaker_status(chat_id) else "🔴 خاموش"
            antilink_status_str = "🟢 روشن" if await get_antilink_status(chat_id) else "🔴 خاموش"
            anti_ad_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_ad") else "🔴 خاموش"
            anti_curse_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_curse") else "🔴 خاموش"
            anti_hung_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_hung") else "🔴 خاموش"
            anti_emoji_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_emoji") else "🔴 خاموش"
            anti_edit_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_edit") else "🔴 خاموش"
            anti_mention_status = "🟢 روشن" if await get_rule_status(chat_id, "anti_mention") else "🔴 خاموش"
            gif_status = "🟢 روشن" if await get_rule_status(chat_id, "gif") else "🔴 خاموش"
            learn_count = len(await list_learnings(chat_id) or [])
            bot_status_chat = await get_bot_status(chat_id)
            bot_status_str = "🟢 روشن" if bot_status_chat == "on" else "🔴 خاموش"
            assistant_admins = await _execute("SELECT COUNT(*) FROM assistant_admins WHERE chat_id=?", (chat_id,), fetch_one=True)
            assistant_count = assistant_admins[0] if assistant_admins else 0
            commands_count = len(await list_custom_commands(chat_id) or [])
            await message.reply(
                f"🎯 **وضعیت فعلی گروه** 🤖\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👑 سازنده : {creator_name}\n"
                f"🛡️ ادمین‌های کمکی : {assistant_count} نفر\n"
                f"🤖 وضعیت ربات : {bot_status_str}\n"
                f"💬 وضعیت سخنگو : {speaker_status_str}\n"
                f"🔗 وضعیت ضد لینک : {antilink_status_str}\n"
                f"📢 وضعیت ضد تبلیغ : {anti_ad_status}\n"
                f"🤬 وضعیت ضد فحش : {anti_curse_status}\n"
                f"⚠️ وضعیت ضد هنگی : {anti_hung_status}\n"
                f"😀 وضعیت ضد ایموجی : {anti_emoji_status}\n"
                f"✏️ وضعیت ضد ویرایش : {anti_edit_status}\n"
                f"📛 وضعیت ضد منشن : {anti_mention_status}\n"
                f"🎬 وضعیت ضد گیف : {gif_status}\n"
                f"📚 تعداد یادگیری‌ها : {learn_count}\n"
                f"⚙️ دستورات سفارشی : {commands_count}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👨‍💻 سازنده ربات: @nicot_com"
            )
            return True

    # انگیزشی
    elif text == "انگیزشی":
        try:
            response = await send_request("http://haji-api.ir/angizeshi")
            if isinstance(response, str):
                await message.reply(response)
            else:
                await message.reply(response.get("result", "متن انگیزشی دریافت نشد."))
        except:
            await message.reply("⚠️ خطا در دریافت متن انگیزشی.")
        return True

    # ارز و دلار
    elif text in ["ارز", "دلار"]:
        try:
            response = await send_request("http://api.codebazan.ir/arz/?type=arz")
            currencies = response.get("Result", [])
            if currencies:
                text_msg = "💰 **نرخ ارزهای رایج امروز** 💰\n\n"
                for idx, currency in enumerate(currencies, 1):
                    text_msg += f"🔹 [{idx}]: {currency['name']} = {currency['price']} تومان\n"
                text_msg += "\n📌 آخرین نرخ ارزها - بروز رسانی لحظه‌ای! ⏳"
            else:
                text_msg = "اطلاعاتی دریافت نشد."
            await message.reply(text_msg)
        except Exception as e:
            await message.reply(f"⚠️ خطا: {str(e)}")
        return True

    # اخبار
    elif text == "اخبار":
        try:
            response = await send_request("https://api-free.ir/api2/news.php?token=f9b4a870986af3276d4806b4962799fe")
            news_list = response if isinstance(response, list) else response.get("result", [])
            if news_list:
                text_msg = "📰 **اخبار روز:**\n\n"
                for i, item in enumerate(news_list, 1):
                    text_msg += f"🔹 [{i}]: {item.get('title', 'بدون عنوان')}\n"
            else:
                text_msg = "⚠️ هیچ خبری یافت نشد."
            await message.reply(text_msg)
        except Exception as e:
            await message.reply(f"⚠️ خطا در دریافت اخبار: {str(e)}")
        return True

    # عکس
    elif text.startswith("عکس"):
        try:
            topic = text.replace("عکس", "").strip()
            if not topic:
                await message.reply("❌ لطفاً موضوعی برای دریافت عکس وارد کنید!")
                return True
            await message.reply("⏳ لطفا منتظر باشید...")
            response = await send_request(f"http://api-free.ir/api/img.php?text={topic}&v=3.5")
            images = response.get("result", [])
            if images:
                url = random.choice(images)
                await message.reply(f"🖼 **عکس با موضوع '{topic}':**\n{url}")
            else:
                await message.reply("⚠️ هیچ تصویری برای این موضوع پیدا نشد.")
        except Exception as e:
            await message.reply(f"⚠️ خطا: {str(e)}")
        return True

    # بیوگرافی
    elif text in ["بیوگرافی", "بیو"]:
        try:
            response = await send_request("https://api.codebazan.ir/bio")
            if isinstance(response, str):
                await message.reply(response)
            else:
                await message.reply(response.get("result", "بیوگرافی دریافت نشد."))
        except:
            await message.reply("⚠️ خطا در دریافت بیوگرافی.")
        return True

    # وضعیتم (تحلیل احساسات تصادفی)
    elif text == "وضعیتم":
        try:
            emotions = [
                "هیجان", "عصبانیت", "فعالیت ذهنی", "افسردگی", "انرژی",
                "خشم", "شادی", "اعتماد به نفس", "تنهایی", "استرس",
                "امید", "عشق", "متغیر", "خستگی", "فشار ذهنی",
                "دلزدگی", "خجالت", "نیاز به حمایت", "گیجی", "تردید",
                "نفرت", "انگیزه", "بی‌حوصلگی", "اجتماعی بودن", "کنجکاوی",
                "تمرکز"
            ]
            emotions_data = {emotion: random.randint(0, 100) for emotion in emotions}
            kol = sum(emotions_data.values()) / len(emotions_data)
            text_lines = "\n".join([f"🔹 {key}: {value}%" for key, value in emotions_data.items()])
            final_text = f"""🎭 **تحلیل احساسات شما** 🎭
━━━━━━━━━━━━━━━
{text_lines}
━━━━━━━━━━━━━━━
📢 **حالت کلی شما:** {kol:.1f}%
🎭 احساسات متغیرند، فردا بهتر خواهد شد! 💖"""
            await message.reply(final_text)
        except Exception as e:
            await message.reply(f"⚠️ خطا در تحلیل احساسات: {str(e)}")
        return True

    # تولد
    elif text.startswith('تولد'):
        try:
            t = text.replace("تولد", "").strip()
            if "/" not in t:
                await message.reply("❌ فرمت را اشتباه وارد کردی! نمونه‌ی درست: تولد 1385/10/10")
                return True
            parts = t.split('/')
            if len(parts) != 3 or not all(i.isdigit() for i in parts):
                await message.reply("❌ فرمت را اشتباه وارد کردی! نمونه‌ی درست: تولد 1385/10/10")
                return True
            years, month, day = parts
            response = await send_request(f"https://api.codebazan.ir/birth?year={years}&month={month}&day={day}")
            respect = response.get("results", {})
            if respect:
                text_msg = f"""🎂 **اطلاعات تولد شما** ✨
━━━━━━━━━━━━━━━
📅 سال: {respect.get("Sal", "?")}
📆 ماه: {respect.get("Mah", "?")}
🗓 روز: {respect.get("Roz", "?")}
🎈 روز تولدت: {respect.get("RozHafte", "?")}
⏳ تعداد روزهایی که زنده‌ای: {respect.get("Roze", "?")} روز
🐾 حیوان سال تولدت: {respect.get("HeyvanSal", "?")}
♈ نماد ماه تولدت: {respect.get("NamadMah", "?")}
━━━━━━━━━━━━━━━
زندگی یه سفره، از هر لحظه‌اش لذت ببر! 🌟💖"""
            else:
                text_msg = "اطلاعات تولد دریافت نشد."
            await message.reply(text_msg)
        except Exception as e:
            await message.reply(f"⚠️ خطا: {str(e)}")
        return True

    return None


# ======================== پیام‌های خصوصی ========================
@bot.on_message_private()
async def private_handler(bot: Robot, message: Message):
    chat_id = message.chat_id
    try:
        id_button = message.aux_data.button_id
    except:
        id_button = None
    sender_id = message.sender_id
    text = message.text

    if await is_first_message(chat_id):
        await save_chat_id(chat_id, "private")

    if str(chat_id) == str(ADMIN_CHAT_ID):
        if text in ["/panel", "پنل"]:
            await message.reply_keypad(
                "👑 **پنل مدیریت ربات** 👑\n\nلطفا یک گزینه را انتخاب کنید:",
                keypad=build_admin_panel()
            )
            return

        if id_button:
            if id_button == "stats":
                groups, users = await get_counts()
                total = await get_total_count()
                stats_msg = (
                    f"📊 **آمار لحظه‌ای ربات:**\n\n"
                    f"▫️ تعداد گروه‌ها: {groups}\n"
                    f"▫️ تعداد کاربران: {users}\n"
                    f"▪️ کل چت‌های فعال: {total}"
                )
                await message.reply(stats_msg)
                return

            if id_button == "broadcast_text":
                admin_states[sender_id] = "awaiting_broadcast_text"
                await message.reply("📝 لطفا متن پیام همگانی را ارسال کنید. برای لغو /cancel را بفرستید.")
                return

            if id_button == "broadcast_fwd":
                admin_states[sender_id] = "awaiting_broadcast_forward"
                await message.reply("➡️ لطفا پیامی که می‌خواهید برای همه فوروارد شود را اینجا فوروارد کنید. برای لغو /cancel را بفرستید.")
                return

            if id_button == "close_panel":
                await message.reply("✅ پنل با موفقیت بسته شد.")
                await bot.remove_keypad(message.chat_id)
                return

        admin_state = admin_states.get(sender_id)
        if admin_state:
            if text == "/cancel":
                del admin_states[sender_id]
                await message.reply("❌ عملیات لغو شد.")
                return

            if admin_state == "awaiting_broadcast_text":
                del admin_states[sender_id]
                sent_msg = await message.reply("⏳ در حال ارسال پیام همگانی...")
                all_chats = await get_all_chats()
                total_chats = len(all_chats)
                success_count = 0
                for i, c_id in enumerate(all_chats):
                    try:
                        await bot.send_message(c_id, text)
                        success_count += 1
                        if (i + 1) % 10 == 0:
                            await bot.edit_message_text(chat_id, sent_msg.message_id, f"⏳ در حال ارسال... ({i+1}/{total_chats})")
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.error(f"Failed to send broadcast to {c_id}: {e}")
                await bot.edit_message_text(chat_id, sent_msg.message_id, f"✅ پیام همگانی برای {success_count} از {total_chats} چت با موفقیت ارسال شد.")
                return

            if admin_state == "awaiting_broadcast_forward":
                if not getattr(message, 'forwarded_from', None):
                    await message.reply("❌ لطفاً یک پیام فوروارد شده ارسال کنید. پیام فعلی فوروارد نیست.")
                    del admin_states[sender_id]
                    return

                del admin_states[sender_id]
                sent_msg = await message.reply("⏳ در حال فوروارد همگانی...")
                all_chats = await get_all_chats()
                total_chats = len(all_chats)
                success_count = 0
                # اصلاح: ترتیب پارامترهای forward_messages (مقصد، مبدأ، شناسه پیام)
                for i, c_id in enumerate(all_chats):
                    try:
                        # نکته: در rubka asynco، متد forward_messages به شکل 
                        # forward_messages(chat_id, from_chat_id, message_id) است
                        await bot.forward_messages(c_id, chat_id, message.message_id)
                        success_count += 1
                        if (i + 1) % 10 == 0:
                            await bot.edit_message_text(chat_id, sent_msg.message_id, f"⏳ در حال فوروارد... ({i+1}/{total_chats})")
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.error(f"Failed to forward broadcast to {c_id}: {e}")
                await bot.edit_message_text(chat_id, sent_msg.message_id, f"✅ پیام برای {success_count} از {total_chats} چت با موفقیت فوروارد شد.")
                return

    elif text.startswith("+"):
        from ai_assistant import process_ai_command
        await process_ai_command(message, chat_id, text)
        return

    if text == "/start":
        groups, users = await get_counts()
        total = await get_total_count()
        name = await bot.get_name(chat_id)
        msg = (
            f"سلام **{name}** 👋✨\n"
            "به ربات سخنگو خوش اومدی 🤖💬\n\n"
            "من یه ربات سخنگوی هوشمندم که می‌تونم توی گروه‌هات با بقیه حرف بزنم و حتی ازت یاد بگیرم 😄\n\n"
            "📢 **برای فعال‌سازی من در گروه:**\n"
            "1️⃣ منو به گروهت اضافه کن.\n"
            "2️⃣ دسترسی‌های کامل (ادمین) رو برام فعال کن ✅\n"
            "3️⃣ داخل گروه بنویس: «فعال» تا به عنوان مالک ثبت بشی.\n\n"
            "🤖 **دستور هوش مصنوعی:**\n"
            "+سوال خودت را اینجا بنویس (مثال: +پایتون چیست؟)\n\n"
            "🎮 **بازی‌ها و سرگرمی:**\n"
            "بازی ریاضی - بازی کلمات - بازی حدس عدد\n"
            "فال حافظ - فال روز - معما - لطیفه\n\n"
            "اگه سوالی داشتید داخل گروه بنویس «راهنما» تا راهنمای کامل برات بیاد 💡\n\n"
            f"👨‍💻 **سازنده ربات:** @nicot_com"
        )
        await message.reply_inline(msg, inline_keypad=build_stats_buttons(groups, users, total))
    else:
        if str(sender_id) != str(ADMIN_CHAT_ID):
            await message.reply("سلام! من رو به گروهت اضافه کن تا بتونم اونجا فعالیت کنم. برای دیدن دستورات /start رو بفرست.\n\n🤖 برای پرسش از هوش مصنوعی: +سوال خودت را بنویس")