from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.appwrite_service import AppwriteService
from keyboards.keyboards import get_admin_keyboard
from config.settings import settings

router = Router()

class PaymentStates(StatesGroup):
    waiting_for_receipt = State()

@router.callback_query(F.data == "send_receipt")
async def start_receipt_upload(call: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_receipt)
    await call.message.answer("📸 أرسل الآن صورة واضحة لإشعار التحويل من تطبيق شام كاش:")
    await call.answer()

@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, bot: Bot, state: FSMContext):
    photo = message.photo[-1]
    
    tx = await AppwriteService.create_transaction(
        user_id=message.from_user.id,
        receipt_file_id=photo.file_id,
        images_credited=10
    )
    if not tx.get("$id"):
        await message.answer("❌ حدث خطأ أثناء تسجيل طلب الشحن، حاول مرة أخرى بعد قليل.")
        await state.clear()
        return
    tx_id = tx["$id"]

    admin_caption = (
        f"🔔 **طلب شحن رصيد جديد (#{tx_id})**\n\n"
        f"• المستخدم: {message.from_user.full_name} (@{message.from_user.username or 'بدون يوزرنيم'})\n"
        f"• الآيدي: `{message.from_user.id}`\n"
        f"• الباقة: 10 صورة"
    )
    
    await bot.send_photo(
        chat_id=settings.ADMIN_CHAT_ID,
        photo=photo.file_id,
        caption=admin_caption,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(tx_id)
    )

    await message.answer("✅ تم إرسال الإشعار للإدارة بنجاح! سيتم شحن رصيدك وتنبيهك فور التأكيد.")
    await state.clear()
