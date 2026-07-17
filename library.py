# library.py
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def load_json(filename, default=None):
    """
    بارگذاری یک فایل JSON از پوشه data.
    اگر فایل موجود نباشد یا خطایی رخ دهد، مقدار default بازگردانده می‌شود.
    """
    try:
        with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"⚠️ خطا در بارگذاری {filename}: {e}")
        return default if default is not None else []

# بارگذاری تمام داده‌های سرگرمی از JSON با مقدار پیش‌فرض لیست خالی
philosophical_quotes = load_json("philosophical_quotes.json", default=[])
personality_tests = load_json("personality_tests.json", default={})
hafez_fal = load_json("hafez_fal.json", default=[])
riddles = load_json("riddles.json", default=[])
islamic_rules = load_json("islamic_rules.json", default=[])
prayers = load_json("prayers.json", default=[])
jokes = load_json("jokes.json", default=[])
fun_facts = load_json("fun_facts.json", default=[])
daily_fortunes = load_json("daily_fortunes.json", default=[])
movie_suggestions = load_json("movie_suggestions.json", default=[])
english_tips = load_json("english_tips.json", default=[])
health_tips = load_json("health_tips.json", default=[])
birthday_horoscope = load_json("birthday_horoscope.json", default={})