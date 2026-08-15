from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 حل أسئلة (صورة أو PDF)")],
            [KeyboardButton(text="💳 شحن رصيد"), KeyboardButton(text="👤 حسابي والرصيد")],
            [KeyboardButton(text="ℹ️ تعليمات الاستخدام")]
        ],
        resize_keyboard=True
    )

def get_buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ لقد قمت بالتحويل، إرسال الإشعار", callback_data="send_receipt")]
        ]
    )

def get_admin_keyboard(tx_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ قبول (+100 صورة)", callback_data=f"pay_accept:{tx_id}"),
                InlineKeyboardButton(text="❌ رفض", callback_data=f"pay_reject:{tx_id}")
            ]
        ]
    )
