import asyncio
import io
import logging
import fitz  # PyMuPDF
from services.ai_service import AIService
from services.image_service import ImageService

logger = logging.getLogger(__name__)

# أقصى عدد صفحات تتحل بنفس الوقت (بالتوازي) بكل ملف. رقم معقول مشان
# ما نضرب حد الطلبات المتزامنة لـ Gemini API ولا نستهلك ذاكرة كتير
# دفعة وحدة على صفحات كبيرة.
MAX_CONCURRENT_PAGES = 5


class PDFService:
    @staticmethod
    async def process_pdf(pdf_bytes: bytes) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        if len(doc) > 10:
            doc.close()
            raise ValueError("الحد الأقصى للملف هو 10 صفحات في المرة الواحدة.")

        # الخطوة 1: نحوّل كل صفحات الـ PDF لصور (عملية محلية سريعة، بدون شبكة)
        page_images: list[bytes] = []
        for page in doc:
            pix = page.get_pixmap(dpi=180)
            page_images.append(pix.tobytes("jpeg"))
        doc.close()

        # الخطوة 2: نحل كل الصور بالتوازي (مش وحدة وحدة بالتسلسل زي قبل)،
        # مع تحديد أقصى عدد طلبات متزامنة مشان نحمي الـ API من الضغط الزايد.
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        async def _solve_page(index: int, img_bytes: bytes):
            async with semaphore:
                try:
                    solutions = await AIService.solve_mcq_image(img_bytes)
                    return index, solutions
                except Exception as e:
                    logger.error(f"Error solving page {index + 1}: {e}")
                    # نرجع نتيجة فاضية للصفحة يلي فشلت، مشان باقي الصفحات
                    # الناجحة ما تنضاع، وبنكمّل بعرضها بدون علامات على هاي الصفحة تحديداً
                    return index, []

        results = await asyncio.gather(
            *(_solve_page(i, img) for i, img in enumerate(page_images))
        )
        # asyncio.gather بيرجع النتائج بنفس ترتيب الإدخال أصلاً، بس منرتبها
        # صراحة عشان الوضوح ومنسحب بس قائمة الحلول لكل صفحة
        results.sort(key=lambda r: r[0])
        solutions_by_page = [solutions for _, solutions in results]

        # الخطوة 3: نعلّم كل صورة بإجاباتها ونجمعهم بملف PDF واحد بنفس ترتيب الصفحات الأصلي
        output_doc = fitz.open()
        for img_bytes, solutions in zip(page_images, solutions_by_page):
            annotated_bytes = ImageService.annotate_image(img_bytes, solutions)

            img_page = fitz.open("jpeg", annotated_bytes)
            rect = img_page[0].rect
            new_page = output_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, stream=annotated_bytes)
            img_page.close()

        output_buffer = io.BytesIO()
        output_doc.save(output_buffer)
        output_doc.close()
        return output_buffer.getvalue()
