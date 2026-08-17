from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 حل أسئلة (صورة أو PDF)")],
            [KeyboardButton(text="👤 حسابي والرصيد")],
            [KeyboardButton(text="ℹ️ تعليمات الاستخدام")]
        ],
        resize_keyboard=True
    )
