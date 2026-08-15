from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.state import default_state
from services.appwrite_service import AppwriteService
from services.redis_service import RedisService
from services.ai_service import AIService
from services.image_service import ImageService
from services.pdf_service import PDFService
import io

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
    finally:
        await status_msg.delete()

@router.message(F.document & (F.document.mime_type == "application/pdf"), default_state)
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
    finally:
        await status_msg.delete()