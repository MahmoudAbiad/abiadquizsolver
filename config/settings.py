from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int
    GEMINI_API_KEY: str
    REDIS_URL: str
    SHAM_CASH_ACCOUNT: str
    SHAM_CASH_QR_URL: str = ""
    FREE_DAILY_LIMIT: int = 3
    PAID_PACKAGE_AMOUNT: int = 100

    # Appwrite Settings
    APPWRITE_ENDPOINT: str = "https://cloud.appwrite.io/v1"
    APPWRITE_PROJECT_ID: str
    APPWRITE_API_KEY: str
    APPWRITE_DATABASE_ID: str = "main_db"
    APPWRITE_USERS_COLLECTION_ID: str = "users"
    APPWRITE_TX_COLLECTION_ID: str = "transactions"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
