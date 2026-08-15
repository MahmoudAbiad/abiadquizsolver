from pydantic import BaseModel, Field
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
            "Analyze this multiple-choice exam page. For every question present:\n"
            "1. Determine the single correct answer based on high academic accuracy.\n"
            "2. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000) "
            "covering the correct choice circle, bullet, or option letter (e.g. A, B, C, D)."
        )

        response = await client.aio.models.generate_content(
            model='gemini-3.7-flash',
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
