import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from handlers import start, ads, admin
from middlewares.ban_check import BanMiddleware

async def set_commands(bot: Bot):
    # إعداد قائمة الأوامر التي تظهر في زر (Menu)
    commands = [
        BotCommand(command="start", description="بدء التشغيل وعرض القائمة"),
        BotCommand(command="create_ad", description="إنشاء إعلان جديد"),
        BotCommand(command="my_ads", description="عرض إعلاناتي")
    ]
    await bot.set_my_commands(commands)

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")
        
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # 1. تفعيل بوابة الحظر
    ban_middleware = BanMiddleware()
    dp.message.middleware(ban_middleware)
    dp.callback_query.middleware(ban_middleware)
    dp.inline_query.middleware(ban_middleware)
    
    # 2. تسجيل مسارات الأوامر (مرة واحدة فقط)
    dp.include_router(start.router)
    dp.include_router(ads.router)
    dp.include_router(admin.router) 
    
    # تسجيل الأوامر عند تشغيل البوت
    await set_commands(bot)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())