# config.py
from rubka.asynco import Robot

DB_PATH = "chats.db"
ADMIN_CHAT_ID = "b0I2Q5o06GO00dc1115da1e913f043e9"
ADMIN_ID = [ADMIN_CHAT_ID]
CHANNEL_LINK = "@bot_nora"
CHANNEL_CREATOR = "@nicot_com"
AI_API_URL = "https://api-free.ir/api/chat.php"

bot = Robot(
    "BBFHDB0MTARWQYPLTLLPKXIHPBEYAPMLZJLXVAZYSVNVGGKFENGLNFOREECFFGYL",
    enable_offset=True,
    max_msg_age=9000
)