from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    # مفتاح واحد قديم (للتوافق الرجعي فقط، إذا ما حددت GEMINI_API_KEYS)
    GEMINI_API_KEY: str = ""
    # عدة مفاتيح Gemini مفصولة بفواصل، كل مفتاح تابع لحساب مختلف، مشان
    # نوزّع الحمل ونتجنب الاصطدام بـ rate limit حساب واحد عند معالجة ملف
    # فيه أكتر من صفحة بالتوازي. مثال: KEY_1,KEY_2,KEY_3
    GEMINI_API_KEYS: str = ""
    REDIS_URL: str
    SHAM_CASH_ACCOUNT: str
    SHAM_CASH_QR_URL: str = ""
    FREE_DAILY_LIMIT: int = 10
    PAID_PACKAGE_AMOUNT: int = 100
    # أقصى عدد صفحات مسموح بالملف الواحد
    MAX_PDF_PAGES: int = 60
    # حد الـ RPD (طلبات باليوم) لكل مفتاح Gemini على الخطة المجانية.
    # 20 هو الرقم الظاهر فعلياً بلوحة Google AI Studio لموديلات
    # gemini-3.5-flash / gemini-3.6-flash بتاريخ هالإعداد. لو Google غيّرت
    # الرقم لاحقاً، عدّل هون بس (ما في حاجة تعدّل كود).
    GEMINI_DAILY_LIMIT_PER_KEY: int = 20
    # كم صفحة نجمع بنداء Gemini واحد بدل نداء لكل صفحة (يوفر كوتا كتير)
    PDF_PAGES_PER_BATCH: int = 5

    # Appwrite Settings
    APPWRITE_ENDPOINT: str = "https://cloud.appwrite.io/v1"
    APPWRITE_PROJECT_ID: str
    APPWRITE_API_KEY: str
    APPWRITE_DATABASE_ID: str = "main_db"
    APPWRITE_USERS_COLLECTION_ID: str = "users"
    APPWRITE_TX_COLLECTION_ID: str = "transactions"
    # كولكشن سجل نشاطات المستخدمين (خاص بلوحة الإدمن الخاصة)
    APPWRITE_LOGS_COLLECTION_ID: str = "activity_logs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def GEMINI_API_KEYS_LIST(self) -> list[str]:
        """قائمة مفاتيح Gemini النظيفة (بعد إزالة الفراغات والفواصل الزايدة).
        إذا ما تم تعريف GEMINI_API_KEYS، بيرجع لمفتاح GEMINI_API_KEY القديم
        كخيار احتياطي مشان التوافق الرجعي."""
        keys = [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]
        if not keys and self.GEMINI_API_KEY:
            keys = [self.GEMINI_API_KEY]
        return keys

settings = Settings()

if not settings.GEMINI_API_KEYS_LIST:
    raise ValueError(
        "لازم تحدد GEMINI_API_KEYS (مفتاح أو أكتر مفصولين بفواصل) أو GEMINI_API_KEY."
    )
