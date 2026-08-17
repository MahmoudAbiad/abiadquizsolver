from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from keyboards.keyboards import get_main_keyboard
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await AppwriteService.get_or_create_user(
        user_id=user_id,
        full_name=message.from_user.full_name,
        username=message.from_user.username
    )

    welcome_text = (
        f"أهلاً بك يا {message.from_user.first_name} في بوت حل الأسئلة المؤتمتة 🎓\n\n"
        "أرسل لي صورة امتحان أو ملف PDF مؤتمت، وسأقوم بوضع علامة خضراء فوراً على الإجابات الصحيحة!\n\n"
        "🎁 لديك 10 صور او ملفات مجانية يومياً تتجدد تلقائياً."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "👤 حسابي والرصيد")
@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    free_left = await RedisService.get_remaining_free_quota(user_id)

    msg = (
        f"📊 **تفاصيل حسابك:**\n\n"
        f"• الرصيد المجاني المتبقي لليوم: **{free_left} صور**\n\n"
        "💡 يتجدد رصيدك المجاني تلقائياً كل يوم."
    )
    await message.answer(msg, parse_mode="Markdown")

@router.message(F.text == "ℹ️ تعليمات الاستخدام")
async def show_help(message: Message):
    help_text = (
        "📖 **تعليمات الاستخدام:**\n\n"
        "1. تأكد من أن صورة الأسئلة واضحة ومقروءة بشكل جيد.\n"
        "2. البوت مخصص حصراً للأسئلة المؤتمتة (اختيار من متعدد MCQ).\n"
        "3. يمكنك إرسال ملفات PDF حتى 10 صفحات وسيعالجها صفحة صفحة.\n"
        "4. لديك رصيد مجاني يومي يتجدد تلقائياً كل يوم."
    )
    await message.answer(help_text, parse_mode="Markdown")
