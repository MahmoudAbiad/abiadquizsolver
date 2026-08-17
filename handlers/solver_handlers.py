from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.state import default_state
from config.settings import settings
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService
from services.ai_service import AIService, get_num_keys
from services.gemini_quota_service import GeminiQuotaService
from services.image_service import ImageService
from services.pdf_service import PDFService
from services.activity_service import ActivityService
import io
import traceback

router = Router()

async def check_and_consume_quota(user_id: int) -> bool:
    deducted = await AppwriteService.deduct_balance(user_id)
    if deducted:
        return True
        
    free_remaining = await RedisService.get_remaining_free_quota(user_id)
    if free_remaining > 0:
        await RedisService.increment_free_usage(user_id)
        return True

    return False

# استقبال الصور فقط في الحالة العادية (Default State)
@router.message(F.photo, default_state)
async def handle_photo(message: Message, bot: Bot):
    user_id = message.from_user.id

    # تحقق سريع من وجود كوتا Gemini يومية متبقية *قبل* ما نخصم من رصيد
    # المستخدم، مشان ما نخصم رصيده على طلب أصلاً رح يفشل
    if await GeminiQuotaService.get_total_remaining(get_num_keys()) <= 0:
        await message.answer("⚠️ نفدت طاقة الحل المتاحة لليوم، يرجى المحاولة لاحقاً 🙏")
        return

    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        await message.answer(
            f"⚠️ لقد استهلكت رصيدك المجاني لليوم ({settings.FREE_DAILY_LIMIT} محاولات). "
            "يرجى شحن الرصيد للمتابعة 💳."
        )
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
        await message.reply_photo(
            photo=output_file,
            caption=(
                f"✅ تم الحل بنجاح! تم تحديد {len(solutions)} سؤال.\n\n"
                "⚠️ هذا حل تلقائي بالذكاء الاصطناعي وقد يحتوي على أخطاء، "
                "خصوصاً بالمواد الصعبة أو الأسئلة الملتبسة. يُرجى مراجعة الإجابات قبل اعتمادها."
            )
        )
    except Exception as e:
        await message.answer(f"❌ حدث خطأ أثناء المعالجة: {str(e)}")
        await ActivityService.log_event(
            user_id=user_id,
            event_type="error",
            full_name=message.from_user.full_name or "",
            username=message.from_user.username or "",
            details=f"خطأ أثناء حل صورة: {str(e)}"[:500],
            error_trace=traceback.format_exc(),
        )
    finally:
        await status_msg.delete()

@router.message(F.document & (F.document.mime_type == "application/pdf"), default_state)
async def handle_pdf(message: Message, bot: Bot):
    user_id = message.from_user.id
    
    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        await message.answer(
            f"⚠️ لقد استهلكت رصيدك المجاني لليوم ({settings.FREE_DAILY_LIMIT} محاولات). "
            "يرجى شحن الرصيد للمتابعة 💳."
        )
        return

    status_msg = await message.answer("⏳ جاري قراءة ملف الـ PDF وحل صفحاته...")

    # عدّاد بسيط لتحديث رسالة الحالة كل 5 صفحات (مش كل صفحة)، مشان
    # ما نصطدم بحد تيليجرام لتعديل الرسائل (rate limit) بملف فيه صفحات كتير
    async def _on_progress(solved: int, total: int):
        if solved == total or solved % 5 == 0:
            try:
                await status_msg.edit_text(f"⏳ جاري الحل... تم إنجاز {solved} من {total} صفحة")
            except Exception:
                pass  # ممكن تفشل لو الرسالة ما تغيّر مضمونها أو rate limit، بلا ما يوقف الحل

    try:
        file_io = io.BytesIO()
        await bot.download(message.document, destination=file_io)
        pdf_bytes = file_io.getvalue()

        solved_pdf = await PDFService.process_pdf(pdf_bytes, progress_callback=_on_progress)
        output_file = BufferedInputFile(solved_pdf, filename="solved_exam.pdf")
        await message.reply_document(
            document=output_file,
            caption=(
                "✅ تم حل جميع صفحات الملف بنجاح!\n\n"
                "⚠️ هذا حل تلقائي بالذكاء الاصطناعي وقد يحتوي على أخطاء، "
                "خصوصاً بالمواد الصعبة أو الأسئلة الملتبسة. يُرجى مراجعة الإجابات قبل اعتمادها."
            )
        )
    except Exception as e:
        await message.answer(f"❌ حدث خطأ أثناء معالجة الملف: {str(e)}")
        await ActivityService.log_event(
            user_id=user_id,
            event_type="error",
            full_name=message.from_user.full_name or "",
            username=message.from_user.username or "",
            details=f"خطأ أثناء حل PDF: {str(e)}"[:500],
            error_trace=traceback.format_exc(),
        )
    finally:
        await status_msg.delete()