import asyncio
import io
import gc
import logging
import fitz  # PyMuPDF
from services.ai_service import AIService
from services.image_service import ImageService

logger = logging.getLogger(__name__)

# حصر المعالجة بصفحتين فقط بنفس اللحظة لتفادي انهيار الرام 512MB
MAX_CONCURRENT_PAGES = 2

class PDFService:
    @staticmethod
    async def process_pdf(pdf_bytes: bytes) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        
        # التحقق من عدد الصفحات
        if total_pages > 15:
            doc.close()
            raise ValueError("عذراً، الحد الأقصى للملف هو 15 صفحة.")

        # 1. تحويل الصفحات لصور بدقة مخفضة ومناسبة جداً (DPI 130)
        page_images: list[bytes] = []
        for page in doc:
            pix = page.get_pixmap(dpi=130)
            page_images.append(pix.tobytes("jpeg"))
            del pix  # تفريغ كائن الصورة من الرام فوراً
        doc.close()

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        async def _solve_page(index: int, img_bytes: bytes):
            async with semaphore:
                # محاولة الحل مع إعادة المحاولة لمرة واحدة في حال واجه النموذج ضغطاً
                for attempt in range(2):
                    try:
                        solutions = await AIService.solve_mcq_image(img_bytes)
                        return index, solutions
                    except Exception as e:
                        logger.warning(f"خطأ في الصفحة {index + 1} (المحاولة {attempt + 1}): {e}")
                        if attempt == 0:
                            await asyncio.sleep(1.5)  # انتظار ثانية ونصف قبل إعادة المحاولة
                return index, []

        # 2. تشغيل المعالجة بتزامن خفيف (صفحتين فقط معاً)
        results = await asyncio.gather(
            *(_solve_page(i, img) for i, img in enumerate(page_images))
        )
        results.sort(key=lambda r: r[0])

        # 3. بناء ملف الـ PDF النهائي وتظليل الإجابات
        output_doc = fitz.open()
        for img_bytes, (_, solutions) in zip(page_images, results):
            annotated_bytes = ImageService.annotate_image(img_bytes, solutions)
            img_page = fitz.open("jpeg", annotated_bytes)
            rect = img_page[0].rect
            new_page = output_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, stream=annotated_bytes)
            img_page.close()
            del annotated_bytes  # تفريغ بايتات الصورة المعالجة

        # تحفيز بايثون لتنظيف الذاكرة (Garbage Collector)
        gc.collect()

        # 4. حفظ الناتج مع ضغط الحجم
        output_buffer = io.BytesIO()
        output_doc.save(output_buffer, garbage=3, deflate=True)
        output_doc.close()
        return output_buffer.getvalue()