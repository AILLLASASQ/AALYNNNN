import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import start, ads

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")
        
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(start.router)
    dp.include_router(ads.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())