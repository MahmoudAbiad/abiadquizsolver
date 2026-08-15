import io
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
