# games.py
import random
import time

from database import add_user_xp
from state import user_games

# ==================== توابع بازی‌ها و مینی‌گیم‌ها ====================
async def start_math_game(chat_id, user_id):
    """بازی ریاضی"""
    num1 = random.randint(10, 99)
    num2 = random.randint(10, 99)
    answer = num1 + num2
    game_id = f"math_{chat_id}_{user_id}_{int(time.time())}"
    
    user_games[game_id] = {
        "type": "math",
        "answer": answer,
        "chat_id": chat_id,
        "user_id": user_id,
        "start_time": time.time()
    }
    
    return {
        "game_id": game_id,
        "question": f"🧮 **بازی ریاضی**\n\n{num1} + {num2} = ?",
        "answer": answer
    }

async def start_word_game(chat_id, user_id):
    """بازی کلمات"""
    words = ["کتاب", "مدرسه", "رایانه", "پایتون", "گلستان", "تهران", "ایران", "دانشگاه"]
    word = random.choice(words)
    # اصلاح: درهم‌ریختن بدون حذف کاراکترهای تکراری
    chars = list(word)
    random.shuffle(chars)
    scrambled = ''.join(chars)
    
    game_id = f"word_{chat_id}_{user_id}_{int(time.time())}"
    user_games[game_id] = {
        "type": "word",
        "answer": word,
        "chat_id": chat_id,
        "user_id": user_id,
        "start_time": time.time()
    }
    
    return {
        "game_id": game_id,
        "question": f"🔤 **بازی کلمات**\n\nکلمه اصلی: {scrambled}",
        "answer": word
    }

async def start_guess_number_game(chat_id, user_id):
    """بازی حدس عدد"""
    number = random.randint(1, 100)
    game_id = f"guess_{chat_id}_{user_id}_{int(time.time())}"
    
    user_games[game_id] = {
        "type": "guess_number",
        "answer": number,
        "chat_id": chat_id,
        "user_id": user_id,
        "start_time": time.time(),
        "hints": 0
    }
    
    return {
        "game_id": game_id,
        "question": f"🔢 **بازی حدس عدد**\n\nمن یک عدد بین 1 تا 100 فکر کردم، حدس بزن چیست؟",
        "answer": number
    }

async def check_game_answer(game_id, user_id, answer):
    """بررسی پاسخ بازی"""
    if game_id not in user_games:
        return False, "❌ این بازی یافت نشد یا زمان آن تمام شده!"
    
    game = user_games[game_id]
    if game["user_id"] != user_id:
        return False, "❌ این بازی مخصوص شما نیست!"
    
    if time.time() - game["start_time"] > 120:  # 2 دقیقه
        del user_games[game_id]
        return False, "⏰ زمان بازی تمام شد!"
    
    correct = False
    if game["type"] == "math":
        correct = str(answer).strip() == str(game["answer"])
    elif game["type"] == "word":
        correct = str(answer).strip().lower() == game["answer"].lower()
    elif game["type"] == "guess_number":
        try:
            guess = int(answer)
            if guess == game["answer"]:
                correct = True
            elif guess < game["answer"]:
                game["hints"] += 1
                return False, f"📈 عدد بزرگ‌تر حدس بزن! (تلاش: {game['hints']})"
            else:
                game["hints"] += 1
                return False, f"📉 عدد کوچک‌تر حدس بزن! (تلاش: {game['hints']})"
        except:
            return False, "❌ لطفاً یک عدد وارد کن!"
    
    if correct:
        # افزودن جایزه
        await add_user_xp(game["chat_id"], user_id, 20)
        del user_games[game_id]
        return True, "🎉 **آفرین! پاسخ درست بود!**\n✨ ۲۰ امتیاز تجربه دریافت کردی!"
    
    return False, "❌ پاسخ اشتباه است، دوباره تلاش کن!"