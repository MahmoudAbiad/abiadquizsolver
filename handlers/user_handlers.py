from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from keyboards.keyboards import get_main_keyboard, get_buy_keyboard
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService
from config.settings import settings

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
        "🎁 لديك 3 صور مجانية يومياً تتجدد تلقائياً."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "👤 حسابي والرصيد")
@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    paid = await AppwriteService.get_user_balance(user_id)
    free_left = await RedisService.get_remaining_free_quota(user_id)

    msg = (
        f"📊 **تفاصيل حسابك:**\n\n"
        f"• الرصيد المجاني المتبقي لليوم: **{free_left} صور**\n"
        f"• الرصيد المدفوع الدائم: **{paid} صورة**\n\n"
        "💡 عند إرسال أي صورة، يتم استهلاك الرصيد المدفوع أولاً ثم المجاني."
    )
    await message.answer(msg, parse_mode="Markdown")

@router.message(F.text == "ℹ️ تعليمات الاستخدام")
async def show_help(message: Message):
    help_text = (
        "📖 **تعليمات الاستخدام:**\n\n"
        "1. تأكد من أن صورة الأسئلة واضحة ومقروءة بشكل جيد.\n"
        "2. البوت مخصص حصراً للأسئلة المؤتمتة (اختيار من متعدد MCQ).\n"
        "3. يمكنك إرسال ملفات PDF حتى 10 صفحات وسيعالجها صفحة صفحة.\n"
        "4. للشحن، اضغط على زر '💳 شحن رصيد' واتبع التعليمات."
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(F.text == "💳 شحن رصيد")
async def buy_balance(message: Message):
    text = (
        f"💳 **شحن رصيد البوت عبر شام كاش**\n\n"
        f"• الباقة: **100 صورة**\n"
        f"• السعر: **0.1$** (أو ما يعادله بالليرة السورية)\n"
        f"• رقم حساب شام كاش: `{settings.SHAM_CASH_ACCOUNT}`\n\n"
        "قم بالتحويل للحساب أعلاه، ثم اضغط على الزر أدناه لإرسال لقطة شاشة إشعار الدفع."
    )
    if settings.SHAM_CASH_QR_URL:
        await message.answer_photo(photo=settings.SHAM_CASH_QR_URL, caption=text, parse_mode="Markdown", reply_markup=get_buy_keyboard())
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=get_buy_keyboard())
