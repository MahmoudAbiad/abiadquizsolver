import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from appwrite.query import Query
from appwrite.id import ID

from services.appwrite_service import databases, _doc_to_dict
from config.settings import settings

logger = logging.getLogger(__name__)

DAMASCUS_TZ = ZoneInfo("Asia/Damascus")

# أنواع الأحداث المسجّلة + تسميتها وأيقونتها بالعربي (للعرض بلوحة الإدمن فقط)
EVENT_LABELS = {
    "start": ("🚀", "بدأ استخدام البوت (/start)"),
    "button": ("🔘", "ضغط زر"),
    "callback": ("🔘", "ضغط زر تفاعلي"),
    "text": ("💬", "رسالة نصية"),
    "upload_photo": ("📷", "أرسل صورة للحل"),
    "upload_document": ("📄", "أرسل ملف PDF للحل"),
    "bot_sent_photo": ("🖼️", "استلم صورة من البوت"),
    "bot_sent_document": ("📁", "استلم ملف من البوت"),
    "error": ("🐞", "حصل خطأ بالبوت أثناء تعامله معه"),
}


def format_damascus_time(iso_str: str | None) -> str:
    """يحوّل توقيت Appwrite (UTC, ISO 8601) لتوقيت دمشق للعرض بلوحة الإدمن."""
    if not iso_str:
        return "غير معروف"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_damascus = dt.astimezone(DAMASCUS_TZ)
        return dt_damascus.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str


class ActivityService:
    DB_ID = settings.APPWRITE_DATABASE_ID
    LOGS_COL = settings.APPWRITE_LOGS_COLLECTION_ID

    @classmethod
    async def log_event(
        cls,
        user_id: int,
        event_type: str,
        full_name: str = "",
        username: str | None = None,
        details: str = "",
        file_id: str | None = None,
        file_type: str | None = None,
        error_trace: str | None = None,
    ) -> None:
        """يسجّل حدث نشاط بشكل غير معطّل (fire-and-forget بالمعنى الوظيفي):
        أي فشل بالتسجيل ما لازم يوقف تشغيل البوت أو يوصل خطأ للمستخدم."""

        def _op():
            try:
                databases.create_document(
                    database_id=cls.DB_ID,
                    collection_id=cls.LOGS_COL,
                    document_id=ID.unique(),
                    data={
                        "telegram_id": user_id,
                        "full_name": (full_name or "")[:256],
                        "username": username or "",
                        "event_type": event_type,
                        "details": (details or "")[:1900],
                        "file_id": file_id or "",
                        "file_type": file_type or "",
                        "error_trace": (error_trace or "")[:4900],
                    },
                )
            except Exception as e:
                logger.error(f"Error logging activity event ({event_type}) for {user_id}: {e}")

        try:
            await asyncio.to_thread(_op)
        except Exception as e:
            logger.error(f"Unexpected failure in log_event: {e}")

    @classmethod
    async def get_recent(cls, limit: int = 8, offset: int = 0) -> list[dict]:
        def _op():
            try:
                res = databases.list_documents(
                    cls.DB_ID, cls.LOGS_COL,
                    queries=[
                        Query.order_desc("$createdAt"),
                        Query.limit(limit),
                        Query.offset(offset),
                    ],
                )
                return [_doc_to_dict(d) for d in res.documents]
            except Exception as e:
                logger.error(f"Error in get_recent: {e}")
                return []
        return await asyncio.to_thread(_op)

    @classmethod
    async def get_user_events(cls, user_id: int, limit: int = 8, offset: int = 0) -> list[dict]:
        def _op():
            try:
                res = databases.list_documents(
                    cls.DB_ID, cls.LOGS_COL,
                    queries=[
                        Query.equal("telegram_id", user_id),
                        Query.order_desc("$createdAt"),
                        Query.limit(limit),
                        Query.offset(offset),
                    ],
                )
                return [_doc_to_dict(d) for d in res.documents]
            except Exception as e:
                logger.error(f"Error in get_user_events: {e}")
                return []
        return await asyncio.to_thread(_op)

    @classmethod
    async def get_log_by_id(cls, log_id: str) -> dict | None:
        def _op():
            try:
                return _doc_to_dict(databases.get_document(cls.DB_ID, cls.LOGS_COL, log_id))
            except Exception as e:
                logger.error(f"Error in get_log_by_id: {e}")
                return None
        return await asyncio.to_thread(_op)
