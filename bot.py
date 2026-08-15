import asyncio
import logging
from aiogram import Bot, Dispatcher
from config.settings import settings
from handlers import user_handlers, solver_handlers, payment_handlers, admin_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Register Routers
    dp.include_router(user_handlers.router)
    dp.include_router(solver_handlers.router)
    dp.include_router(payment_handlers.router)
    dp.include_router(admin_handlers.router)

    logging.info("Bot is connected to Appwrite and ready for exam solving!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
