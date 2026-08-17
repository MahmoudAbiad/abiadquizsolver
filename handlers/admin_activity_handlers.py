from aiogram import Router, Bot
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)

from config.settings import settings
from services.activity_service import ActivityService, EVENT_LABELS, format_damascus_time

router = Router()

PAGE_SIZE = 6


class IsAdmin(Filter):
    """فلتر بيخلي كل هالراوتر يشتغل حصراً على حساب الإدمن (ADMIN_CHAT_ID)
    ولا يستجيب لأي حد غيره، حتى لو خمّن نفس الأوامر."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user) and user.id == settings.ADMIN_CHAT_ID


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminActivityStates(StatesGroup):
    waiting_for_user_id = State()


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕒 آخر نشاطات المستخدمين", callback_data="adm:recent:0")],
            [InlineKeyboardButton(text="👤 نشاط مستخدم معيّن", callback_data="adm:askuser")],
        ]
    )


def _back_button(extra_row: list[InlineKeyboardButton] | None = None) -> list[list[InlineKeyboardButton]]:
    rows = [extra_row] if extra_row else []
    rows.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="adm:menu")])
    return rows


def _format_entry(idx: int, log: dict) -> str:
    icon, label = EVENT_LABELS.get(log.get("event_type"), ("❔", log.get("event_type", "غير معروف")))
    name = log.get("full_name") or "بدون اسم"
    username = log.get("username") or ""
    uname_part = f" (@{username})" if username else ""
    time_str = format_damascus_time(log.get("$createdAt"))
    details = log.get("details") or ""

    text = (
        f"{idx}. {icon} <b>{label}</b>\n"
        f"   👤 {name}{uname_part} — <code>{log.get('telegram_id')}</code>\n"
        f"   🕒 {time_str} (توقيت دمشق)"
    )
    if details and log.get("event_type") not in ("upload_photo",):
        safe_details = details.replace("<", "‹").replace(">", "›")
        text += f"\n   📝 {safe_details}"
    return text


def _build_list_keyboard(logs: list[dict], nav_prefix: str, offset: int, has_more: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    action_row: list[InlineKeyboardButton] = []
    for i, log in enumerate(logs, start=1):
        if log.get("file_id"):
            action_row.append(InlineKeyboardButton(text=f"📂 فتح ملف #{i}", callback_data=f"adm:file:{log['$id']}"))
        elif log.get("event_type") == "error":
            action_row.append(InlineKeyboardButton(text=f"🐞 تفاصيل خطأ #{i}", callback_data=f"adm:err:{log['$id']}"))
        if len(action_row) == 2:
            rows.append(action_row)
            action_row = []
    if action_row:
        rows.append(action_row)

    nav_row: list[InlineKeyboardButton] = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ الأحدث", callback_data=f"{nav_prefix}:{max(0, offset - PAGE_SIZE)}"))
    if has_more:
        nav_row.append(InlineKeyboardButton(text="الأقدم ▶️", callback_data=f"{nav_prefix}:{offset + PAGE_SIZE}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def admin_entry(message: Message):
    await message.answer(
        "🛠️ <b>لوحة مراقبة النشاطات (خاصة فيك فقط)</b>\n\nاختر شو بدك تعرض:",
        reply_markup=_main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "adm:menu")
async def admin_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "🛠️ <b>لوحة مراقبة النشاطات (خاصة فيك فقط)</b>\n\nاختر شو بدك تعرض:",
        reply_markup=_main_menu_keyboard(),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("adm:recent:"))
async def show_recent(call: CallbackQuery):
    offset = int(call.data.split(":")[2])
    logs = await ActivityService.get_recent(limit=PAGE_SIZE, offset=offset)

    if not logs and offset == 0:
        await call.message.edit_text(
            "لا يوجد أي نشاط مسجّل حتى الآن.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=_back_button()),
        )
        await call.answer()
        return

    has_more = len(logs) == PAGE_SIZE
    body = "\n\n".join(_format_entry(i, log) for i, log in enumerate(logs, start=offset + 1))
    text = f"🕒 <b>آخر نشاطات المستخدمين</b> (دفعة {offset + 1}–{offset + len(logs)})\n\n{body}"

    await call.message.edit_text(
        text,
        reply_markup=_build_list_keyboard(logs, "adm:recent", offset, has_more),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(lambda c: c.data == "adm:askuser")
async def ask_user_id(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminActivityStates.waiting_for_user_id)
    await call.message.edit_text(
        "✏️ ابعتلي آيدي المستخدم (رقم التيليغرام)، أو حوّل (forward) لأي رسالة منه مباشرة:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=_back_button()),
    )
    await call.answer()


@router.message(AdminActivityStates.waiting_for_user_id)
async def receive_user_id(message: Message, state: FSMContext):
    target_id = None

    if message.forward_origin and getattr(message.forward_origin, "sender_user", None):
        target_id = message.forward_origin.sender_user.id
    elif message.text and message.text.strip().lstrip("-").isdigit():
        target_id = int(message.text.strip())

    if target_id is None:
        await message.answer("⚠️ ما قدرت أفهم الآيدي. ابعت رقم التيليغرام مباشرة أو حوّل رسالة من المستخدم.")
        return

    await state.clear()
    await _render_user_activity(message, target_id, offset=0)


async def _render_user_activity(message: Message, user_id: int, offset: int):
    logs = await ActivityService.get_user_events(user_id, limit=PAGE_SIZE, offset=offset)

    if not logs and offset == 0:
        await message.answer(
            f"لا يوجد أي نشاط مسجّل للمستخدم <code>{user_id}</code>.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=_back_button()),
            parse_mode="HTML",
        )
        return

    has_more = len(logs) == PAGE_SIZE
    body = "\n\n".join(_format_entry(i, log) for i, log in enumerate(logs, start=offset + 1))
    text = f"👤 <b>نشاط المستخدم</b> <code>{user_id}</code> (دفعة {offset + 1}–{offset + len(logs)})\n\n{body}"

    await message.answer(
        text,
        reply_markup=_build_list_keyboard(logs, f"adm:user:{user_id}", offset, has_more),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data.startswith("adm:user:"))
async def show_user_activity_page(call: CallbackQuery):
    _, _, user_id_str, offset_str = call.data.split(":")
    user_id, offset = int(user_id_str), int(offset_str)

    logs = await ActivityService.get_user_events(user_id, limit=PAGE_SIZE, offset=offset)
    has_more = len(logs) == PAGE_SIZE
    body = "\n\n".join(_format_entry(i, log) for i, log in enumerate(logs, start=offset + 1)) or "لا يوجد نشاط بهذه الصفحة."
    text = f"👤 <b>نشاط المستخدم</b> <code>{user_id}</code> (دفعة {offset + 1}–{offset + len(logs)})\n\n{body}"

    await call.message.edit_text(
        text,
        reply_markup=_build_list_keyboard(logs, f"adm:user:{user_id}", offset, has_more),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(lambda c: c.data.startswith("adm:file:"))
async def open_file(call: CallbackQuery, bot: Bot):
    log_id = call.data.split(":", 2)[2]
    log = await ActivityService.get_log_by_id(log_id)

    if not log or not log.get("file_id"):
        await call.answer("⚠️ الملف غير موجود أو انتهت صلاحيته.", show_alert=True)
        return

    caption = (
        f"📁 ملف من نشاط المستخدم <code>{log.get('telegram_id')}</code>\n"
        f"👤 {log.get('full_name') or 'بدون اسم'}"
        + (f" (@{log['username']})" if log.get("username") else "")
        + f"\n🕒 {format_damascus_time(log.get('$createdAt'))} (توقيت دمشق)"
    )

    try:
        if log.get("file_type") == "photo":
            await bot.send_photo(chat_id=settings.ADMIN_CHAT_ID, photo=log["file_id"], caption=caption, parse_mode="HTML")
        else:
            await bot.send_document(chat_id=settings.ADMIN_CHAT_ID, document=log["file_id"], caption=caption, parse_mode="HTML")
        await call.answer()
    except Exception as e:
        await call.answer(f"⚠️ تعذّر فتح الملف: {e}", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("adm:err:"))
async def open_error_details(call: CallbackQuery, bot: Bot):
    log_id = call.data.split(":", 2)[2]
    log = await ActivityService.get_log_by_id(log_id)

    if not log:
        await call.answer("⚠️ السجل غير موجود.", show_alert=True)
        return

    trace = log.get("error_trace") or log.get("details") or "لا توجد تفاصيل إضافية."
    header = (
        f"🐞 تفاصيل الخطأ لدى المستخدم {log.get('telegram_id')} "
        f"بتاريخ {format_damascus_time(log.get('$createdAt'))} (توقيت دمشق):\n\n{trace}"
    )

    if len(header) <= 3800:
        await bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=f"<pre>{header}</pre>", parse_mode="HTML")
    else:
        file_bytes = header.encode("utf-8")
        await bot.send_document(
            chat_id=settings.ADMIN_CHAT_ID,
            document=BufferedInputFile(file_bytes, filename=f"error_{log_id}.txt"),
        )
    await call.answer()
