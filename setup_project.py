import os

files = {
    # -------------------------------------------------------------
    # REQUIREMENTS & DOCKERFILE
    # -------------------------------------------------------------
    "requirements.txt": """aiogram>=3.17.0
google-genai>=1.0.0
Pillow>=10.4.0
PyMuPDF>=1.24.0
redis>=5.0.0
appwrite>=5.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
""",

    ".env.example": """BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
ADMIN_CHAT_ID=123456789
GEMINI_API_KEY=AIzaSy...
REDIS_URL=rediss://default:password@host:port
SHAM_CASH_ACCOUNT=12345678
SHAM_CASH_QR_URL=https://placehold.co/400x400.png?text=Sham+Cash+QR
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=6a7fb79a00047f9a1552
APPWRITE_API_KEY=your_appwrite_api_key_here
APPWRITE_DATABASE_ID=main_db
APPWRITE_USERS_COLLECTION_ID=users
APPWRITE_TX_COLLECTION_ID=transactions
""",

    "Dockerfile": """FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
""",

    # -------------------------------------------------------------
    # CONFIG
    # -------------------------------------------------------------
    "config/settings.py": """from pydantic_settings import BaseSettings, SettingsConfigDict

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
""",

    # -------------------------------------------------------------
    # SERVICES
    # -------------------------------------------------------------
    "services/appwrite_service.py": """import asyncio
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from config.settings import settings

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
                return databases.get_document(cls.DB_ID, cls.USERS_COL, str(user_id))
            except Exception:
                return databases.create_document(
                    database_id=cls.DB_ID,
                    collection_id=cls.USERS_COL,
                    document_id=str(user_id),
                    data={
                        "telegram_id": user_id,
                        "full_name": full_name,
                        "username": username or "",
                        "paid_balance": 0
                    }
                )
        return await asyncio.to_thread(_op)

    @classmethod
    async def get_user_balance(cls, user_id: int) -> int:
        def _op():
            try:
                doc = databases.get_document(cls.DB_ID, cls.USERS_COL, str(user_id))
                return doc.get("paid_balance", 0)
            except Exception:
                return 0
        return await asyncio.to_thread(_op)

    @classmethod
    async def deduct_balance(cls, user_id: int) -> bool:
        def _op():
            try:
                doc = databases.get_document(cls.DB_ID, cls.USERS_COL, str(user_id))
                current = doc.get("paid_balance", 0)
                if current > 0:
                    databases.update_document(
                        cls.DB_ID, cls.USERS_COL, str(user_id),
                        data={"paid_balance": current - 1}
                    )
                    return True
                return False
            except Exception:
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
                
                user_id = str(tx["user_id"])
                user = databases.get_document(cls.DB_ID, cls.USERS_COL, user_id)
                new_bal = user.get("paid_balance", 0) + tx.get("images_credited", 100)
                databases.update_document(cls.DB_ID, cls.USERS_COL, user_id, data={"paid_balance": new_bal})
                
                return tx
            except Exception:
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
            except Exception:
                return None
        return await asyncio.to_thread(_op)
""",

    "services/redis_service.py": """from datetime import datetime
import redis.asyncio as redis
from config.settings import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

class RedisService:
    @staticmethod
    def _get_key(user_id: int) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"free_quota:{user_id}:{today}"

    @classmethod
    async def get_remaining_free_quota(cls, user_id: int) -> int:
        key = cls._get_key(user_id)
        used = await redis_client.get(key)
        used_count = int(used) if used else 0
        return max(0, settings.FREE_DAILY_LIMIT - used_count)

    @classmethod
    async def increment_free_usage(cls, user_id: int):
        key = cls._get_key(user_id)
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        await pipe.execute()
""",

    "services/ai_service.py": """from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config.settings import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

class SolvedQuestion(BaseModel):
    question_number: int
    correct_option: str
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax] coordinates normalized to 0-1000 for the correct choice letter/circle")

class ExamSolutionResponse(BaseModel):
    solutions: list[SolvedQuestion]

class AIService:
    @staticmethod
    async def solve_mcq_image(image_bytes: bytes) -> list[SolvedQuestion]:
        prompt = (
            "Analyze this multiple-choice exam page. For every question present:\\n"
            "1. Determine the single correct answer based on high academic accuracy.\\n"
            "2. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000) "
            "covering the correct choice circle, bullet, or option letter (e.g. A, B, C, D)."
        )

        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExamSolutionResponse,
                temperature=0.1,
            ),
        )
        data: ExamSolutionResponse = response.parsed
        return data.solutions
""",

    "services/image_service.py": """import io
from PIL import Image, ImageDraw
from services.ai_service import SolvedQuestion

class ImageService:
    @staticmethod
    def annotate_image(image_bytes: bytes, solutions: list[SolvedQuestion]) -> bytes:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img)

        for item in solutions:
            ymin, xmin, ymax, xmax = item.box_2d
            
            abs_ymin = int((ymin / 1000) * height)
            abs_xmin = int((xmin / 1000) * width)
            abs_ymax = int((ymax / 1000) * height)
            abs_xmax = int((xmax / 1000) * width)

            center_x = (abs_xmin + abs_xmax) // 2
            center_y = (abs_ymin + abs_ymax) // 2
            radius = max(8, (abs_ymax - abs_ymin) // 3)

            # Draw green indicator
            draw.ellipse(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                fill=(46, 204, 113, 255),
                outline=(39, 174, 96, 255),
                width=2
            )

        watermark_text = "تم الحل بواسطة الذكاء الاصطناعي"
        draw.text((20, height - 35), watermark_text, fill=(120, 120, 120))

        output_buffer = io.BytesIO()
        img.save(output_buffer, format="JPEG", quality=95)
        return output_buffer.getvalue()
""",

    "services/pdf_service.py": """import io
import fitz  # PyMuPDF
from services.ai_service import AIService
from services.image_service import ImageService

class PDFService:
    @staticmethod
    async def process_pdf(pdf_bytes: bytes) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if len(doc) > 10:
            raise ValueError("الحد الأقصى للملف هو 10 صفحات في المرة الواحدة.")

        output_doc = fitz.open()

        for page in doc:
            pix = page.get_pixmap(dpi=180)
            img_bytes = pix.tobytes("jpeg")
            
            solutions = await AIService.solve_mcq_image(img_bytes)
            annotated_bytes = ImageService.annotate_image(img_bytes, solutions)
            
            img_page = fitz.open("jpeg", annotated_bytes)
            rect = img_page[0].rect
            new_page = output_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, stream=annotated_bytes)

        output_buffer = io.BytesIO()
        output_doc.save(output_buffer)
        output_doc.close()
        doc.close()
        return output_buffer.getvalue()
""",

    # -------------------------------------------------------------
    # KEYBOARDS
    # -------------------------------------------------------------
    "keyboards/keyboards.py": """from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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
""",

    # -------------------------------------------------------------
    # HANDLERS
    # -------------------------------------------------------------
    "handlers/user_handlers.py": """from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from keyboards.keyboards import get_main_keyboard, get_buy_keyboard
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService
from config.settings import settings

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await AppwriteService.get_or_create_user(
        user_id=user_id,
        full_name=message.from_user.full_name,
        username=message.from_user.username
    )

    welcome_text = (
        f"أهلاً بك يا {message.from_user.first_name} في بوت حل الأسئلة المؤتمتة 🎓\\n\\n"
        "أرسل لي صورة امتحان أو ملف PDF مؤتمت، وسأقوم بوضع علامة خضراء فوراً على الإجابات الصحيحة!\\n\\n"
        "🎁 لديك 3 صور مجانية يومياً تتجدد تلقائياً."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "👤 حسابي والرصيد")
@router.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    paid = await AppwriteService.get_user_balance(user_id)
    free_left = await RedisService.get_remaining_free_quota(user_id)

    msg = (
        f"📊 **تفاصيل حسابك:**\\n\\n"
        f"• الرصيد المجاني المتبقي لليوم: **{free_left} صور**\\n"
        f"• الرصيد المدفوع الدائم: **{paid} صورة**\\n\\n"
        "💡 عند إرسال أي صورة، يتم استهلاك الرصيد المدفوع أولاً ثم المجاني."
    )
    await message.answer(msg, parse_mode="Markdown")

@router.message(F.text == "ℹ️ تعليمات الاستخدام")
async def show_help(message: Message):
    help_text = (
        "📖 **تعليمات الاستخدام:**\\n\\n"
        "1. تأكد من أن صورة الأسئلة واضحة ومقروءة بشكل جيد.\\n"
        "2. البوت مخصص حصراً للأسئلة المؤتمتة (اختيار من متعدد MCQ).\\n"
        "3. يمكنك إرسال ملفات PDF حتى 10 صفحات وسيعالجها صفحة صفحة.\\n"
        "4. للشحن، اضغط على زر '💳 شحن رصيد' واتبع التعليمات."
    )
    await message.answer(help_text, parse_mode="Markdown")

@router.message(F.text == "💳 شحن رصيد")
async def buy_balance(message: Message):
    text = (
        f"💳 **شحن رصيد البوت عبر شام كاش**\\n\\n"
        f"• الباقة: **100 صورة**\\n"
        f"• السعر: **0.1$** (أو ما يعادله بالليرة السورية)\\n"
        f"• رقم حساب شام كاش: `{settings.SHAM_CASH_ACCOUNT}`\\n\\n"
        "قم بالتحويل للحساب أعلاه، ثم اضغط على الزر أدناه لإرسال لقطة شاشة إشعار الدفع."
    )
    if settings.SHAM_CASH_QR_URL:
        await message.answer_photo(photo=settings.SHAM_CASH_QR_URL, caption=text, parse_mode="Markdown", reply_markup=get_buy_keyboard())
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=get_buy_keyboard())
""",

    "handlers/solver_handlers.py": """from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService
from services.ai_service import AIService
from services.image_service import ImageService
from services.pdf_service import PDFService
import io

router = Router()

async def check_and_consume_quota(user_id: int) -> bool:
    # Check paid balance first
    deducted = await AppwriteService.deduct_balance(user_id)
    if deducted:
        return True
        
    # Fallback to free daily quota
    free_remaining = await RedisService.get_remaining_free_quota(user_id)
    if free_remaining > 0:
        await RedisService.increment_free_usage(user_id)
        return True

    return False

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    user_id = message.from_user.id
    
    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        await message.answer("⚠️ لقد استهلكت رصيدك المجاني لليوم (3 صور). يرجى شحن الرصيد للمتابعة 💳.")
        return

    status_msg = await message.answer("⏳ جاري تحليل الأسئلة ووضع الإجابات الصحيحة...")
    
    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        img_bytes = file_io.getvalue()

        solutions = await AIService.solve_mcq_image(img_bytes)
        annotated_bytes = ImageService.annotate_image(img_bytes, solutions)

        output_file = BufferedInputFile(annotated_bytes, filename="solved_exam.jpg")
        await message.reply_photo(photo=output_file, caption=f"✅ تم الحل بنجاح! تم تحديد {len(solutions)} سؤال.")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ أثناء المعالجة: {str(e)}")
    finally:
        await status_msg.delete()

@router.message(F.document & (F.document.mime_type == "application/pdf"))
async def handle_pdf(message: Message, bot: Bot):
    user_id = message.from_user.id
    
    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        await message.answer("⚠️ لقد استهلكت رصيدك المتاح. يرجى شحن رصيدك للمتابعة 💳.")
        return

    status_msg = await message.answer("⏳ جاري قراءة ملف الـ PDF وحل صفحاته...")
    
    try:
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        pdf_bytes = file_io.getvalue()

        solved_pdf = await PDFService.process_pdf(pdf_bytes)
        output_file = BufferedInputFile(solved_pdf, filename="solved_exam.pdf")
        await message.reply_document(document=output_file, caption="✅ تم حل جميع صفحات الملف بنجاح!")
    except Exception as e:
        await message.answer(f"❌ حدث خطأ أثناء معالجة الملف: {str(e)}")
    finally:
        await status_msg.delete()
""",

    "handlers/payment_handlers.py": """from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.appwrite_service import AppwriteService
from keyboards.keyboards import get_admin_keyboard
from config.settings import settings

router = Router()

class PaymentStates(StatesGroup):
    waiting_for_receipt = State()

@router.callback_query(F.data == "send_receipt")
async def start_receipt_upload(call: CallbackQuery, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_receipt)
    await call.message.answer("📸 أرسل الآن صورة واضحة لإشعار التحويل من تطبيق شام كاش:")
    await call.answer()

@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, bot: Bot, state: FSMContext):
    photo = message.photo[-1]
    
    tx = await AppwriteService.create_transaction(
        user_id=message.from_user.id,
        receipt_file_id=photo.file_id,
        images_credited=100
    )
    tx_id = tx["$id"]

    admin_caption = (
        f"🔔 **طلب شحن رصيد جديد (#{tx_id})**\\n\\n"
        f"• المستخدم: {message.from_user.full_name} (@{message.from_user.username})\\n"
        f"• الآيدي: `{message.from_user.id}`\\n"
        f"• الباقة: 100 صورة"
    )
    
    await bot.send_photo(
        chat_id=settings.ADMIN_CHAT_ID,
        photo=photo.file_id,
        caption=admin_caption,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(tx_id)
    )

    await message.answer("✅ تم إرسال الإشعار للإدارة بنجاح! سيتم شحن رصيدك وتنبيهك فور التأكيد.")
    await state.clear()
""",

    "handlers/admin_handlers.py": """from aiogram import Router, F, Bot
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
        caption=f"{call.message.caption}\\n\\n✅ **تم قبول الطلب وشحن {tx.get('images_credited', 100)} صورة للمستخدم.**",
        reply_markup=None
    )
    
    await bot.send_message(
        chat_id=int(tx["user_id"]),
        text=f"🎉 **مبروك! تم تأكيد عملية الدفع.**\\nتمت إضافة **{tx.get('images_credited', 100)} صورة** إلى رصيدك بنجاح."
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
            text=f"❌ **تم رفض إشعار الدفع الخاص بك.**\\nالسبب: {reason}"
        )
        await message.reply("✅ تم تسجيل الرفض وإشعار الطالب بالسبب.")

    await state.clear()
""",

    # -------------------------------------------------------------
    # BOT RUNNER
    # -------------------------------------------------------------
    "bot.py": """import asyncio
import logging
from aiogram import Bot, Dispatcher
from config.settings import settings
from handlers import user_handlers, solver_handlers, payment_handlers, admin_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Register Routers
    dp.include_router(user_handlers.router)
    dp.include_router(solver_handlers.router)
    dp.include_router(payment_handlers.router)
    dp.include_router(admin_handlers.router)

    logging.info("Bot is connected to Appwrite and ready for exam solving!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
"""
}

def create_project():
    print("🚀 جاري إنشاء ملفات البوت المربوط مع Appwrite...")
    for path, content in files.items():
        dir_name = os.path.dirname(path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  └── تم إنشاء: {path}")
    print("\n✨ تم تجهيز مشروع Appwrite بنجاح وبدون أي أخطاء!")

if __name__ == "__main__":
    create_project()