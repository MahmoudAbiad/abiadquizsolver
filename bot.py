import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from config.settings import settings
from handlers import user_handlers, solver_handlers, admin_activity_handlers
from middlewares.activity_middleware import IncomingActivityMiddleware, outgoing_file_log_middleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def handle_ping(request):
    return web.Response(text="Bot is running perfectly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"✅ Web server successfully bound to port {port}")

async def main():
    await start_web_server()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # تسجيل نشاطات المستخدمين الواردة (أزرار، صور، ملفات، أخطاء) + الملفات
    # الصادرة من البوت (اللي البوت بيسلمها للمستخدم)، مشان لوحة الإدمن الخاصة
    incoming_logger = IncomingActivityMiddleware()
    dp.message.outer_middleware(incoming_logger)
    dp.callback_query.outer_middleware(incoming_logger)
    bot.session.middleware(outgoing_file_log_middleware)

    # ترتيب الراوترات: لوحة الإدمن الخاصة أولاً، ثم المستخدمين وحل الاختبارات
    dp.include_router(admin_activity_handlers.router)
    dp.include_router(user_handlers.router)
    dp.include_router(solver_handlers.router)

    logging.info("Bot is connected to Appwrite and ready for exam solving!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())