import logging
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config.settings import settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY)

class SolvedQuestion(BaseModel):
    question_number: int
    correct_option: str
    box_2d: list[int] = Field(
        description="[ymin, xmin, ymax, xmax] coordinates normalized to 0-1000 for the FULL answer "
        "option row/line (from the start of the option letter/bullet to the end of the option's "
        "text), not just the letter or bullet alone"
    )

class ExamSolutionResponse(BaseModel):
    solutions: list[SolvedQuestion]

# قائمة النماذج مرتبة حسب الأولوية (Fallback Cascade)
# تم الاقتصار على الموديلين اللي أكّدتهم Google رسمياً كـ GA (عام، مستقر،
# جاهز للإنتاج) بآخر سجل تحديثات لهم (آب 2026):
# https://ai.google.dev/gemini-api/docs/changelog
# أي موديل تاني (متل gemini-3.7-flash، أو حتى gemini-3.5-flash العادي غير
# المؤكد حالياً) تم استبعاده عمداً لأنو مش مضمون يشتغل، وبيضيف تأخير فاشل
# قبل ما يوصل الطلب لموديل شغّال فعلاً.
FALLBACK_MODELS = [
    "gemini-3.6-flash",       # النموذج الأساسي (الأحدث والأدق، GA رسمي)
    "gemini-3.5-flash-lite",  # الاحتياطي (أرخص وأسرع، GA رسمي أيضاً)
]

class AIService:
    @staticmethod
    async def solve_mcq_image(image_bytes: bytes) -> list[SolvedQuestion]:
        prompt = (
            "Analyze this multiple-choice exam page. For every question present:\n"
            "1. Determine the single correct answer based on high academic accuracy.\n"
            "2. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000) "
            "covering the ENTIRE correct answer option's row - starting from the option's "
            "letter/bullet (e.g. A, B, C, D) and extending to include the full text of that "
            "option, not just the letter or bullet by itself."
        )

        last_exception = None

        # تجربة النماذج بالتتابع حتى ينجح أحدها
        for model_name in FALLBACK_MODELS:
            try:
                logger.info(f"Attempting to solve exam with model: {model_name}")
                
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt
                    ],
                    # ملاحظة: بدءاً من gemini-3.6-flash و gemini-3.5-flash-lite،
                    # صارت Google تعتبر temperature/top_p/top_k معطّلة (deprecated)
                    # وبتتجاهلها حالياً، وبأجيال قادمة رح ترجع خطأ إذا انبعتت.
                    # فتم حذفها من هون مشان الكود ما ينكسر بترقية موديل مستقبلية.
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExamSolutionResponse,
                    ),
                )
                
                data: ExamSolutionResponse = response.parsed
                logger.info(f"Successfully solved with {model_name} (found {len(data.solutions)} questions)")
                return data.solutions

            except Exception as e:
                logger.warning(f"Model {model_name} failed or timed out. Error: {str(e)}")
                last_exception = e
                continue

        # في حال فشلت جميع النماذج الاحتياطية
        logger.error("All AI models in the fallback chain failed.")
        raise RuntimeError(f"فشلت جميع نماذج الذكاء الاصطناعي في الاستجابة: {str(last_exception)}")