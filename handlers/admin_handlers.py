from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.appwrite_service import AppwriteService

router = Router()

class AdminRejectState(StatesGroup):
    waiting_for_reason = State()

@router.callback_query(F.data.startswith("pay_accept:"))
async def approve_payment(call: CallbackQuery, bot: Bot):
    tx_id = call.data.split(":")[1]
    tx = await AppwriteService.approve_transaction(tx_id)

    if not tx:
        await call.answer("⚠️ هذا الطلب تمت معالجته مسبقاً أو غير موجود.", show_alert=True)
        return

    await call.message.edit_caption(
        caption=f"{call.message.caption}\n\n✅ **تم قبول الطلب وشحن {tx.get('images_credited', 100)} صورة للمستخدم.**",
        reply_markup=None
    )
    
    await bot.send_message(
        chat_id=int(tx["user_id"]),
        text=f"🎉 **مبروك! تم تأكيد عملية الدفع.**\nتمت إضافة **{tx.get('images_credited', 100)} صورة** إلى رصيدك بنجاح."
    )
    await call.answer("تم شحن الرصيد بنجاح!")

@router.callback_query(F.data.startswith("pay_reject:"))
async def reject_payment_prompt(call: CallbackQuery, state: FSMContext):
    tx_id = call.data.split(":")[1]
    await state.update_data(reject_tx_id=tx_id, admin_msg_id=call.message.message_id)
    await state.set_state(AdminRejectState.waiting_for_reason)
    await call.message.reply("✏️ اكتب سبب الرفض الآن (مثال: رقم العملية غير مطابق / الصورة غير واضحة):")
    await call.answer()

@router.message(AdminRejectState.waiting_for_reason)
async def submit_rejection(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    tx_id = data["reject_tx_id"]
    reason = message.text

    tx = await AppwriteService.reject_transaction(tx_id, reason)

    if tx:
        await bot.send_message(
            chat_id=int(tx["user_id"]),
            text=f"❌ **تم رفض إشعار الدفع الخاص بك.**\nالسبب: {reason}"
        )
        await message.reply("✅ تم تسجيل الرفض وإشعار الطالب بالسبب.")

    await state.clear()
