import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from handlers import start, ads, admin
from middlewares.ban_check import BanMiddleware
from middlewares.throttling import ThrottlingMiddleware

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 القائمة الرئيسية"),
        BotCommand(command="check", description="🔐 رابط القناة والتحقق من الاشتراك")
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
    
    # 2. تفعيل بوابة الانتظار (التحكم بالسبام)
    throttling_middleware = ThrottlingMiddleware(slow_mode_delay=1.0) # يمكنك تغيير 3.0 إلى 5.0
    dp.message.middleware(throttling_middleware)
    dp.callback_query.middleware(throttling_middleware)

    # 3. تسجيل مسارات الأوامر
    dp.include_router(start.router)
    dp.include_router(ads.router)
    dp.include_router(admin.router)
    
    # تسجيل الأوامر عند تشغيل البوت
    await set_commands(bot)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())