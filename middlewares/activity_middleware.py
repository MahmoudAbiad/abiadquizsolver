import logging
import traceback
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.methods import SendDocument, SendPhoto
from aiogram.types import CallbackQuery, Message, TelegramObject

from config.settings import settings
from services.activity_service import ActivityService

logger = logging.getLogger(__name__)

# كاش بسيط بالذاكرة (اسم + يوزرنيم لكل مستخدم) عشان نقدر نعرض اسم المستخدم
# بسجل "الملفات اللي البوت سلّمها" رغم إنه بهالنقطة (طلبات API الصادرة) ما
# عنا غير الـ chat_id. يتحدّث تلقائياً كل ما المستخدم يبعت أي شي للبوت.
_user_info_cache: dict[int, tuple[str, str]] = {}

# نصوص أزرار الكيبورد الرئيسية (تسجيلها كـ "button" بدل "text" عشان توضح بالتقرير)
_KNOWN_BUTTONS = {
    "📷 حل أسئلة (صورة أو PDF)",
    "👤 حسابي والرصيد",
    "ℹ️ تعليمات الاستخدام",
}


class IncomingActivityMiddleware(BaseMiddleware):
    """يسجّل كل نشاط وارد من المستخدمين (أزرار، صور، ملفات، رسائل، أخطاء)
    ما عدا نشاط الإدمن نفسه (حتى ما يتلخبط سجل المستخدمين بضغطاته هو على
    لوحة التحكم)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = user.id if user else None

        if user_id is not None:
            _user_info_cache[user_id] = (user.full_name or "", user.username or "")

        is_admin = user_id == settings.ADMIN_CHAT_ID

        if user_id is not None and not is_admin:
            event_type, details, file_id, file_type = self._extract_event_info(event)
            await ActivityService.log_event(
                user_id=user_id,
                event_type=event_type,
                full_name=user.full_name or "",
                username=user.username or "",
                details=details,
                file_id=file_id,
                file_type=file_type,
            )

        try:
            return await handler(event, data)
        except Exception as e:
            if user_id is not None and not is_admin:
                await ActivityService.log_event(
                    user_id=user_id,
                    event_type="error",
                    full_name=user.full_name or "",
                    username=user.username or "",
                    details=str(e)[:500],
                    error_trace=traceback.format_exc(),
                )
            raise

    @staticmethod
    def _extract_event_info(event: TelegramObject) -> tuple[str, str, str | None, str | None]:
        if isinstance(event, CallbackQuery):
            return "callback", event.data or "", None, None

        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return "start", event.text, None, None
            if event.text in _KNOWN_BUTTONS:
                return "button", event.text, None, None
            if event.photo:
                return "upload_photo", "صورة أرسلها المستخدم للحل", event.photo[-1].file_id, "photo"
            if event.document:
                fname = event.document.file_name or "ملف"
                return "upload_document", fname, event.document.file_id, "document"
            if event.text:
                return "text", event.text[:300], None, None
            return "text", f"[{event.content_type}]", None, None

        return "text", "", None, None


async def outgoing_file_log_middleware(make_request, bot, method):
    """Middleware على مستوى جلسة البوت (Bot session) بيلتقط كل صورة/ملف
    البوت بيرسله لأي مستخدم (مش للإدمن) ويسجله بنشاطه، مشان قسم
    'الملفات اللي المستخدم استلمها من البوت' بلوحة الإدمن."""
    result = await make_request(bot, method)

    try:
        if isinstance(method, (SendPhoto, SendDocument)):
            chat_id = method.chat_id
            if chat_id is not None and int(chat_id) != settings.ADMIN_CHAT_ID:
                file_id = None
                file_type = None
                if isinstance(method, SendPhoto) and getattr(result, "photo", None):
                    file_id = result.photo[-1].file_id
                    file_type = "photo"
                elif isinstance(method, SendDocument) and getattr(result, "document", None):
                    file_id = result.document.file_id
                    file_type = "document"

                if file_id:
                    full_name, username = _user_info_cache.get(int(chat_id), ("", ""))
                    event_type = "bot_sent_photo" if file_type == "photo" else "bot_sent_document"
                    await ActivityService.log_event(
                        user_id=int(chat_id),
                        event_type=event_type,
                        full_name=full_name,
                        username=username,
                        details=(method.caption or "")[:300],
                        file_id=file_id,
                        file_type=file_type,
                    )
    except Exception:
        logger.exception("outgoing_file_log_middleware failed to log outgoing file")

    return result
