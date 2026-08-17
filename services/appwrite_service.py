import asyncio
import logging
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID
from config.settings import settings

logger = logging.getLogger(__name__)

client = Client()
client.set_endpoint(settings.APPWRITE_ENDPOINT)
client.set_project(settings.APPWRITE_PROJECT_ID)
client.set_key(settings.APPWRITE_API_KEY)

databases = Databases(client)


def _doc_to_dict(doc) -> dict:
    """
    نسخة appwrite SDK الحالية (v23+) بترجع كائنات Pydantic (Document / DocumentList)
    مش قواميس (dict) عادية زي قبل. هاد الفنكشن بيحوّل أي Document لقاموس عادي
    { "$id": ..., **الحقول } مشان باقي الكود يضل يشتغل بنفس الطريقة اللي كان فيها
    (doc.get("field"), ...) بدون ما نغيّر كل الهاندلرز.
    """
    data = dict(doc.data)
    data["$id"] = doc.id
    return data


class AppwriteService:
    DB_ID = settings.APPWRITE_DATABASE_ID
    USERS_COL = settings.APPWRITE_USERS_COLLECTION_ID

    @classmethod
    async def get_or_create_user(cls, user_id: int, full_name: str, username: str | None) -> dict:
        def _op():
            try:
                # البحث عن المستخدم برقم التيليغرام
                res = databases.list_documents(
                    cls.DB_ID, cls.USERS_COL,
                    queries=[Query.equal("telegram_id", user_id)]
                )
                if res.documents:
                    return _doc_to_dict(res.documents[0])

                # إنشاء مستخدم جديد إن لم يوجد
                new_doc = databases.create_document(
                    database_id=cls.DB_ID,
                    collection_id=cls.USERS_COL,
                    document_id=ID.unique(),
                    data={
                        "telegram_id": user_id,
                        "full_name": full_name,
                        "username": username or "",
                    }
                )
                return _doc_to_dict(new_doc)
            except Exception as e:
                logger.error(f"Error in get_or_create_user: {e}")
                return {}
        return await asyncio.to_thread(_op)
