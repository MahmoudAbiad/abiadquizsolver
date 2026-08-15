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

class AppwriteService:
    DB_ID = settings.APPWRITE_DATABASE_ID
    USERS_COL = settings.APPWRITE_USERS_COLLECTION_ID
    TX_COL = settings.APPWRITE_TX_COLLECTION_ID

    @classmethod
    async def get_or_create_user(cls, user_id: int, full_name: str, username: str | None) -> dict:
        def _op():
            try:
                # البحث عن المستخدم برقم التيليغرام
                res = databases.list_documents(
                    cls.DB_ID, cls.USERS_COL,
                    queries=[Query.equal("telegram_id", user_id)]
                )
                if res["documents"]:
                    return res["documents"][0]
                
                # إنشاء مستخدم جديد إن لم يوجد
                return databases.create_document(
                    database_id=cls.DB_ID,
                    collection_id=cls.USERS_COL,
                    document_id=ID.unique(),
                    data={
                        "telegram_id": user_id,
                        "full_name": full_name,
                        "username": username or "",
                        "paid_balance": 0
                    }
                )
            except Exception as e:
                logger.error(f"Error in get_or_create_user: {e}")
                return {}
        return await asyncio.to_thread(_op)

    @classmethod
    async def get_user_balance(cls, user_id: int) -> int:
        def _op():
            try:
                res = databases.list_documents(
                    cls.DB_ID, cls.USERS_COL,
                    queries=[Query.equal("telegram_id", user_id)]
                )
                if res["documents"]:
                    return res["documents"][0].get("paid_balance", 0)
                return 0
            except Exception as e:
                logger.error(f"Error in get_user_balance: {e}")
                return 0
        return await asyncio.to_thread(_op)

    @classmethod
    async def deduct_balance(cls, user_id: int) -> bool:
        def _op():
            try:
                res = databases.list_documents(
                    cls.DB_ID, cls.USERS_COL,
                    queries=[Query.equal("telegram_id", user_id)]
                )
                if res["documents"]:
                    doc = res["documents"][0]
                    current = doc.get("paid_balance", 0)
                    if current > 0:
                        databases.update_document(
                            cls.DB_ID, cls.USERS_COL, doc["$id"],
                            data={"paid_balance": current - 1}
                        )
                        return True
                return False
            except Exception as e:
                logger.error(f"Error in deduct_balance: {e}")
                return False
        return await asyncio.to_thread(_op)

    @classmethod
    async def create_transaction(cls, user_id: int, receipt_file_id: str, images_credited: int = 100) -> dict:
        def _op():
            return databases.create_document(
                database_id=cls.DB_ID,
                collection_id=cls.TX_COL,
                document_id=ID.unique(),
                data={
                    "user_id": user_id,
                    "receipt_file_id": receipt_file_id,
                    "images_credited": images_credited,
                    "status": "PENDING",
                    "rejection_reason": ""
                }
            )
        return await asyncio.to_thread(_op)

    @classmethod
    async def approve_transaction(cls, tx_id: str) -> dict | None:
        def _op():
            try:
                tx = databases.get_document(cls.DB_ID, cls.TX_COL, tx_id)
                if tx.get("status") != "PENDING":
                    return None
                
                databases.update_document(cls.DB_ID, cls.TX_COL, tx_id, data={"status": "APPROVED"})
                
                # جلب وثيقة المستخدم عبر telegram_id وتحديث رصيدها
                user_id = tx["user_id"]
                res = databases.list_documents(
                    cls.DB_ID, cls.USERS_COL,
                    queries=[Query.equal("telegram_id", user_id)]
                )
                if res["documents"]:
                    user_doc = res["documents"][0]
                    new_bal = user_doc.get("paid_balance", 0) + tx.get("images_credited", 100)
                    databases.update_document(cls.DB_ID, cls.USERS_COL, user_doc["$id"], data={"paid_balance": new_bal})
                
                return tx
            except Exception as e:
                logger.error(f"Error in approve_transaction: {e}")
                return None
        return await asyncio.to_thread(_op)

    @classmethod
    async def reject_transaction(cls, tx_id: str, reason: str) -> dict | None:
        def _op():
            try:
                tx = databases.get_document(cls.DB_ID, cls.TX_COL, tx_id)
                if tx.get("status") != "PENDING":
                    return None
                databases.update_document(
                    cls.DB_ID, cls.TX_COL, tx_id,
                    data={"status": "REJECTED", "rejection_reason": reason}
                )
                return tx
            except Exception as e:
                logger.error(f"Error in reject_transaction: {e}")
                return None
        return await asyncio.to_thread(_op)