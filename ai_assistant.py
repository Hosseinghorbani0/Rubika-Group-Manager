import logging
from rubka.asynco import Message
from config import bot

logger = logging.getLogger(__name__)

async def process_ai_command(message: Message, chat_id: str, text: str) -> bool:
    """پردازش دستورات مرتبط با هوش مصنوعی"""
    from utils import ask_ai_question # To avoid circular import for now
    
    if text.startswith("+"):
        try:
            question = text[1:].strip()
            if not question:
                await message.reply("❌ لطفاً سوال خود را بعد از علامت + وارد کنید.")
                return True
            processing_msg = await message.reply("🤖 در حال پردازش سوال شما... لطفاً صبر کنید.")
            ai_response = await ask_ai_question(question)
            try:
                await bot.delete_message(chat_id, processing_msg.message_id)
            except:
                pass
            await message.reply(f"🤖 **پاسخ هوش مصنوعی:**\n\n{ai_response}")
        except Exception as e:
            await message.reply(f"❌ خطا در ارتباط با هوش مصنوعی: {str(e)}")
            logger.error(f"AI Error: {e}")
        return True
    
    return False
