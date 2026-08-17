import asyncio
import io
import gc
import logging
import math
from typing import Callable, Optional
import fitz  # PyMuPDF
from config.settings import settings
from services.ai_service import AIService, get_num_keys
from services.gemini_quota_service import GeminiQuotaService
from services.image_service import ImageService

logger = logging.getLogger(__name__)

# نربط عدد الدفعات المعالَجة بالتوازي بعدد مفاتيح Gemini المتاحة (دفعة
# لكل مفتاح بنفس اللحظة تقريباً)، بس نحطّلها سقف أعلى (4) لأن الرام لسا
# 512MB على خطة Render المجانية بغض النظر عن عدد المفاتيح.
MAX_CONCURRENT_BATCHES = min(4, max(2, get_num_keys()))


def _render_pages_to_jpeg(pdf_bytes: bytes, max_pages: int) -> list[bytes]:
    """تحويل صفحات الـ PDF لصور JPEG. عملية CPU-bound (PyMuPDF) فبتنفّذ
    بخيط منفصل عن طريق asyncio.to_thread، مشان ما تعلّق حلقة الأحداث
    وتوقف استقبال/رد باقي المستخدمين طول فترة معالجة ملف كبير."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total_pages = len(doc)
        if total_pages > max_pages:
            raise ValueError(f"عذراً، الحد الأقصى للملف هو {max_pages} صفحة.")

        page_images: list[bytes] = []
        for page in doc:
            pix = page.get_pixmap(dpi=130)
            page_images.append(pix.tobytes("jpeg"))
            del pix
        return page_images
    finally:
        doc.close()


def _build_output_pdf(page_images: list[bytes], solutions_by_page: list[list]) -> bytes:
    """بناء ملف الـ PDF النهائي المُظلَّل (بخيط منفصل لنفس سبب الرندرة)."""
    output_doc = fitz.open()
    try:
        for img_bytes, solutions in zip(page_images, solutions_by_page):
            annotated_bytes = ImageService.annotate_image(img_bytes, solutions)
            img_page = fitz.open("jpeg", annotated_bytes)
            rect = img_page[0].rect
            new_page = output_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, stream=annotated_bytes)
            img_page.close()
            del annotated_bytes

        gc.collect()

        output_buffer = io.BytesIO()
        output_doc.save(output_buffer, garbage=3, deflate=True)
        return output_buffer.getvalue()
    finally:
        output_doc.close()


class PDFService:
    @staticmethod
    async def process_pdf(
        pdf_bytes: bytes,
        progress_callback: Optional[Callable[[int, int], "asyncio.Future"]] = None,
    ) -> bytes:
        """
        progress_callback(solved_count, total_pages): كول-باك اختياري (async)
        بينادى بعد كل ما تنحل دفعة صفحات، مشان تحدّث رسالة الحالة للمستخدم.
        """
        # 1. تحويل الصفحات لصور (بخيط منفصل)
        page_images = await asyncio.to_thread(
            _render_pages_to_jpeg, pdf_bytes, settings.MAX_PDF_PAGES
        )
        total_pages = len(page_images)

        # 2. تقسيم الصفحات لدفعات (batches) - نداء واحد لـ Gemini يحل عدة
        # صفحات دفعة وحدة بدل نداء منفصل لكل صفحة، مشان نوفّر الكوتا
        # اليومية المحدودة جداً بالخطة المجانية (RPD).
        batch_size = max(1, settings.PDF_PAGES_PER_BATCH)
        batches: list[list[int]] = [
            list(range(i, min(i + batch_size, total_pages)))
            for i in range(0, total_pages, batch_size)
        ]
        needed_calls = len(batches)

        # 3. تحقق من الكوتا المتوفرة فعلياً قبل ما نبلش (بدل ما نبلش
        # ونفشل بالنص ونضيع كوتا اليوم على شغل ناقص)
        num_keys = get_num_keys()
        remaining_quota = await GeminiQuotaService.get_total_remaining(num_keys)
        if needed_calls > remaining_quota:
            max_pages_now = remaining_quota * batch_size
            raise ValueError(
                f"عذراً، الكوتا اليومية المتاحة حالياً تكفي لحوالي {max_pages_now} صفحة بس "
                f"(الملف فيه {total_pages} صفحة). جرب ملف أصغر أو حاول تاني بعد إعادة "
                "تعيين الكوتا اليومية."
            )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
        solved_pages_count = 0
        progress_lock = asyncio.Lock()
        solutions_by_page: list[list] = [[] for _ in range(total_pages)]

        async def _solve_batch(batch_page_indices: list[int]):
            nonlocal solved_pages_count
            batch_images = [page_images[i] for i in batch_page_indices]

            async with semaphore:
                grouped = {}
                for attempt in range(2):
                    try:
                        grouped = await AIService.solve_mcq_batch(batch_images)
                        break
                    except Exception as e:
                        logger.warning(
                            f"خطأ بدفعة الصفحات {batch_page_indices} (المحاولة {attempt + 1}): {e}"
                        )
                        if attempt == 0:
                            await asyncio.sleep(1.5)

            for local_idx, global_idx in enumerate(batch_page_indices):
                solutions_by_page[global_idx] = grouped.get(local_idx, [])

            if progress_callback is not None:
                async with progress_lock:
                    solved_pages_count += len(batch_page_indices)
                    try:
                        await progress_callback(solved_pages_count, total_pages)
                    except Exception:
                        logger.warning("فشل تحديث رسالة التقدّم", exc_info=True)

        # 4. تشغيل الدفعات بتزامن محدود
        await asyncio.gather(*(_solve_batch(b) for b in batches))

        # 5. بناء ملف الـ PDF النهائي (بخيط منفصل)
        return await asyncio.to_thread(_build_output_pdf, page_images, solutions_by_page)
