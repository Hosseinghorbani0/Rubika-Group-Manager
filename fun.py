# fun.py
import random
import jdatetime

from library import (
    daily_fortunes, jokes, fun_facts, movie_suggestions,
    english_tips, health_tips, prayers, islamic_rules,
    philosophical_quotes, riddles, hafez_fal,
    personality_tests, birthday_horoscope
)

# ==================== توابع سرگرمی ====================
async def get_random_fortune():
    """فال روزانه"""
    if daily_fortunes:
        return random.choice(daily_fortunes)
    return "⚠️ فال روزانه در دسترس نیست."

async def get_random_joke():
    """لطیفه تصادفی"""
    if jokes:
        return random.choice(jokes)
    return "⚠️ لطیفه‌ای یافت نشد."

async def get_random_fact():
    """حقیقت جالب"""
    if fun_facts:
        return random.choice(fun_facts)
    return "⚠️ حقیقت جالبی موجود نیست."

async def get_random_movie():
    """پیشنهاد فیلم"""
    if movie_suggestions:
        return random.choice(movie_suggestions)
    return "⚠️ پیشنهاد فیلمی یافت نشد."

async def get_english_tip():
    """نکته آموزشی انگلیسی"""
    if english_tips:
        return random.choice(english_tips)
    return "⚠️ نکته انگلیسی موجود نیست."

async def get_health_tip():
    """نکته سلامتی"""
    if health_tips:
        return random.choice(health_tips)
    return "⚠️ نکته سلامتی موجود نیست."

async def get_random_prayer():
    """دعای تصادفی"""
    if prayers:
        return random.choice(prayers)
    return "⚠️ دعایی یافت نشد."

async def get_random_islamic_rule():
    """حکم شرعی تصادفی"""
    if islamic_rules:
        return random.choice(islamic_rules)
    return "⚠️ حکم شرعی یافت نشد."

async def get_random_philosophy():
    """جمله فلسفی"""
    if philosophical_quotes:
        return random.choice(philosophical_quotes)
    return "⚠️ جمله فلسفی یافت نشد."

async def get_riddle_answer(question):
    """جواب معما"""
    if not riddles:
        return "⚠️ معماها در دسترس نیستند."
    for riddle in riddles:
        if riddle["question"] == question:
            return f"🔍 **جواب معمای قبلی:**\n{riddle['answer']}"
    return None

async def get_hafez_fal():
    """فال حافظ"""
    if hafez_fal:
        return random.choice(hafez_fal)
    return None  # در handler بررسی می‌شود

async def get_personality_test(category, choice):
    """تست شخصیت"""
    if not personality_tests:
        return None
    if category in personality_tests and choice in personality_tests[category]:
        traits = personality_tests[category][choice]
        return (
            f"🎭 **تست شخصیت - {category}**\n\n"
            f"شما رنگ {choice} را انتخاب کردید:\n"
            f"• {traits[0]}\n"
            f"• {traits[1]}\n"
            f"• {traits[2]}\n"
            f"{traits[3]}"
        )
    return None

async def get_birthday_horoscope(month):
    """طالع بینی ماه تولد"""
    if not birthday_horoscope:
        return None
    if month in birthday_horoscope:
        info = birthday_horoscope[month]
        return (
            f"♈ **طالع بینی متولدین {month}** ♈\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔮 **نماد:** {info['symbol']}\n"
            f"🔥 **عنصر:** {info['element']}\n"
            f"👤 **شخصیت:** {info['personality']}\n"
            f"🍀 **روز خوش شانس:** {info['lucky_day']}"
        )
    return None

# ==================== توابع کاربردی ====================
async def calculate_age(birth_year, birth_month, birth_day):
    """محاسبه سن دقیق"""
    try:
        today = jdatetime.date.today()
        birth_date = jdatetime.date(int(birth_year), int(birth_month), int(birth_day))
        age = today.year - birth_date.year

        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        next_birthday = jdatetime.date(today.year, birth_date.month, birth_date.day)
        if next_birthday < today:
            next_birthday = jdatetime.date(today.year + 1, birth_date.month, birth_date.day)

        days_to_birthday = (next_birthday - today).days

        return {
            "age": age,
            "days_to_birthday": days_to_birthday,
            "next_birthday": next_birthday.strftime("%Y/%m/%d")
        }
    except:
        return None

async def get_qibla_direction():
    """جهت قبله"""
    return (
        "🕋 **جهت قبله**\n\n"
        "برای شهر تهران، قبله در جهت **جنوب غربی** (حدود ۲۱۵ درجه) است.\n\n"
        "نکات:\n"
        "• برای تشخیص دقیق از اپلیکیشن‌های قبله‌یاب استفاده کنید\n"
        "• در ایران، جهت تقریبی قبله بین جنوب و غرب است\n"
        "• می‌توانید از سمت خورشید در ظهر شرعی کمک بگیرید"
    )

async def get_ramadan_info():
    """اطلاعات ماه رمضان"""
    today = jdatetime.date.today()
    try:
        ramadan_start = jdatetime.date(today.year, 9, 1)
    except:
        ramadan_start = jdatetime.date(today.year, 9, 1)

    if today > ramadan_start:
        try:
            ramadan_start = jdatetime.date(today.year + 1, 9, 1)
        except:
            ramadan_start = jdatetime.date(today.year, 9, 1)

    days_until = (ramadan_start - today).days

    return (
        f"☪️ **اطلاعات ماه مبارک رمضان**\n\n"
        f"📅 شروع ماه رمضان: {ramadan_start.strftime('%Y/%m/%d')}\n"
        f"⏳ مانده تا رمضان: {days_until} روز\n\n"
        f"🌙 اعمال ماه رمضان:\n"
        f"• روزه‌داری از اذان صبح تا مغرب\n"
        f"• خواندن دعای سحر و افطار\n"
        f"• تلاوت قرآن کریم\n"
        f"• شب‌زنده‌داری در شب‌های قدر\n\n"
        f"🤲 دعای روزهای رمضان:\n"
        f"اللهم اجعل صیامی فیه صیام الصائمین..."
    )