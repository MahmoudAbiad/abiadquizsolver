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
        description="[ymin, xmin, ymax, xmax] coordinates normalized to 0-1000 for the correct choice letter/circle"
    )

class ExamSolutionResponse(BaseModel):
    solutions: list[SolvedQuestion]

# قائمة النماذج مرتبة حسب الأولوية (Fallback Cascade)
FALLBACK_MODELS = [
    "gemini-3.7-flash",       # النموذج الأساسي
    "gemini-3.6-flash",       # الاحتياطي الأول
    "gemini-3.5-flash-lite",       # الاحتياطي الثاني
]

class AIService:
    @staticmethod
    async def solve_mcq_image(image_bytes: bytes) -> list[SolvedQuestion]:
        prompt = (
            "Analyze this multiple-choice exam page. For every question present:\n"
            "1. Determine the single correct answer based on high academic accuracy.\n"
            "2. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000) "
            "covering the correct choice circle, bullet, or option letter (e.g. A, B, C, D)."
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
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExamSolutionResponse,
                        temperature=0.1,
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