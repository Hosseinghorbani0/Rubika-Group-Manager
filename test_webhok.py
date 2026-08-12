from rubka import Robot, Message
bot=Robot("BDFHAD0WSKKEYFITBMWUNXFZWMXQULHRHMLCUPORWUMIUARBXXFBBOTYTKJVTAZU",web_hook="https://hosseinghorbani0.ir/Rubi_bot/Nora")
me = bot.get_me()
print(me)
@bot.on_message()
async def test(bot:Robot,message:Message):
    print(message.__dict__)


bot.run()