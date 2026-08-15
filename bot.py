import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from config.settings import settings
from handlers import user_handlers, solver_handlers, payment_handlers, admin_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# مسار بسيط لإرضاء سيرفر Render Web Service
async def handle_ping(request):
    return web.Response(text="Bot is alive and running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web health check server running on port {port}")

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Register Routers
    dp.include_router(user_handlers.router)
    dp.include_router(solver_handlers.router)
    dp.include_router(payment_handlers.router)
    dp.include_router(admin_handlers.router)

    # تشغيل خادم الويب والبوت معاً في الخلفية
    await start_web_server()

    logging.info("Bot is connected to Appwrite and ready for exam solving!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())