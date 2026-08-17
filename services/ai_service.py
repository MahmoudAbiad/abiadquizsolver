import itertools
import logging
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config.settings import settings
from services.gemini_quota_service import GeminiQuotaService

logger = logging.getLogger(__name__)

# تجهيز عميل (Client) منفصل لكل مفتاح API، مع الاحتفاظ برقم كل مفتاح
# (index) مشان نقدر نتتبع كوتا كل مفتاح لحاله بـ GeminiQuotaService.
_api_keys = settings.GEMINI_API_KEYS_LIST
_clients = [genai.Client(api_key=key) for key in _api_keys]
_indexed_clients = list(enumerate(_clients))  # [(0, client0), (1, client1), ...]
_client_cycle = itertools.cycle(_indexed_clients)

logger.info(f"AIService initialized with {len(_clients)} Gemini API key(s).")


def _get_next_client() -> tuple[int, genai.Client]:
    """توزيع دوري (Round Robin) على المفاتيح المتاحة. آمن هون لأن الكود
    كله شغال بحلقة أحداث asyncio وحيدة (single event loop) بدون threads،
    فما في تزاحم فعلي على next(). بيرجع (رقم المفتاح، العميل) مشان نقدر
    نتتبع كوتا هالمفتاح بالذات."""
    return next(_client_cycle)


def get_num_keys() -> int:
    return len(_clients)


class SolvedQuestion(BaseModel):
    # 0-based: رقم الصورة (الصفحة) جوا الدفعة (batch) يلي انبعتت بنفس
    # النداء. لما يكون النداء لصورة وحدة بس (solve_mcq_image)، القيمة هاي
    # مهملة (ما منستخدمها).
    page_index: int = Field(
        default=0,
        description="0-based index of the image this question belongs to, "
        "in the order the images were provided in this request",
    )
    question_number: int
    reasoning: str = Field(
        description="Brief step-by-step reasoning (1-3 sentences) explaining WHY this option "
        "is correct, based on the specific academic subject/terminology shown on the page, "
        "written BEFORE deciding on correct_option. Consider and rule out the other options "
        "explicitly if the question is ambiguous or the terminology is highly specialized."
    )
    correct_option: str
    box_2d: list[int] = Field(
        description="[ymin, xmin, ymax, xmax] coordinates normalized to 0-1000, RELATIVE TO "
        "THAT SPECIFIC IMAGE's own width/height (not the whole batch), for the FULL answer "
        "option row/line (from the start of the option letter/bullet to the end of the option's "
        "text), not just the letter or bullet alone"
    )

class ExamSolutionResponse(BaseModel):
    solutions: list[SolvedQuestion]

# حوض النماذج المتاحة. gemini-3.1-pro-preview هو الأقوى بالاستدلال
# (reasoning) وهو المفروض يكون الخيار الأساسي دايماً لأن حل امتحانات
# فعلية (مش قراءة مفتاح إجابات جاهز) بيحتاج دقة أكاديمية عالية، خصوصاً
# بمواد متخصصة. باقي الموديلات (flash) موجودة بس كخط احتياط لو الـ Pro
# فشل أو خلصت كوتته اليومية، مشان البوت يضل شغال حتى لو بدقة أقل.
MODEL_POOL = [
    "gemini-3.1-pro-preview",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

# مستوى التفكير (thinking) لكل موديل. الموديلات القوية (Pro) لازم أعلى
# مستوى تفكير ممكن لأن هاد أهم عامل بيرفع دقتها بأسئلة متخصصة. flash
# منخليها HIGH كمان لأنها هي خط الدفاع الثاني وبنفس الوقت رح تحل محل
# الـ Pro بحال فشل، فمنفضل الدقة على السرعة بكل الحالات هون.
_THINKING_LEVEL = types.ThinkingLevel.HIGH


def _fallback_chain_for_key(key_index: int) -> list[str]:
    """بترجع ترتيب النماذج المستخدمة لهالمفتاح بالذات: تبلش دايماً
    بـ gemini-3.1-pro-preview (الأدق)، وإذا فشل (خطأ، كوتا نفدت...)
    بتنزل تدريجياً لموديلات flash كاحتياط، بدل ما يفشل الطلب كلياً."""
    return MODEL_POOL

_SINGLE_PROMPT = (
    "Analyze this multiple-choice exam page. It is a real, unanswered exam (no answers are "
    "pre-marked) — you must solve it yourself with high academic rigor. First identify the "
    "specific subject/field being tested (it could be any field — medicine, engineering, law, "
    "history, languages, etc. — and may be written in Arabic or another language) and apply "
    "that field's precise terminology and conventions; do not guess from surface-level or "
    "generic familiarity with a term — reason carefully about the specific definition being "
    "tested within that subject. For every question present:\n"
    "1. First think step-by-step (in the `reasoning` field) about what the question is "
    "precisely testing, and briefly evaluate why the other options are wrong before settling "
    "on an answer.\n"
    "2. Determine the single correct answer based on that reasoning.\n"
    "3. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000) "
    "covering the ENTIRE correct answer option's row - starting from the option's "
    "letter/bullet (e.g. A, B, C, D) and extending to include the full text of that "
    "option, not just the letter or bullet by itself."
)


def _batch_prompt(num_images: int) -> str:
    return (
        f"You will receive {num_images} images, each a separate page of a real, unanswered "
        "multiple-choice exam (no answers are pre-marked), given in order starting at index 0 "
        "(first image = page_index 0, second image = page_index 1, and so on). First identify "
        "the specific subject/field being tested on each page (it could be any field — "
        "medicine, engineering, law, history, languages, etc. — and may be written in Arabic "
        "or another language) and apply that field's precise terminology and conventions; do "
        "not guess from surface-level or generic familiarity with a term — reason carefully "
        "about the specific definition being tested within that subject. Analyze EACH image "
        "independently and completely — do not skip any image. For every question found on "
        "ANY of the images:\n"
        "1. First think step-by-step (in the `reasoning` field) about what the question is "
        "precisely testing, and briefly evaluate why the other options are wrong before "
        "settling on an answer.\n"
        "2. Determine the single correct answer based on that reasoning.\n"
        "3. Set page_index to the 0-based index of the image that question appears on.\n"
        "4. Identify the exact bounding box [ymin, xmin, ymax, xmax] (normalized to 1000, "
        "relative to THAT SPECIFIC image's own width/height, not the combined set) covering "
        "the ENTIRE correct answer option's row - starting from the option's letter/bullet "
        "(e.g. A, B, C, D) and extending to include the full text of that option, not just "
        "the letter or bullet by itself."
    )


async def _call_gemini(contents: list, key_index: int, client: genai.Client) -> ExamSolutionResponse:
    last_exception = None
    for model_name in _fallback_chain_for_key(key_index):
        try:
            logger.info(f"Attempting to solve with model: {model_name} (key #{key_index})")
            # نسجّل استهلاك الكوتا لهالمفتاح قبل الإرسال مباشرة، لأن غوغل
            # بتحسب الطلب على الـ RPD حتى لو رجع خطأ من جوّا (429 مثلاً)
            await GeminiQuotaService.increment(key_index)

            response = await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                # ملاحظة: بدءاً من gemini-3.6-flash و gemini-3.5-flash-lite،
                # صارت Google تعتبر temperature/top_p/top_k معطّلة (deprecated)
                # وبتتجاهلها حالياً، وبأجيال قادمة رح ترجع خطأ إذا انبعتت.
                # فتم حذفها من هون مشان الكود ما ينكسر بترقية موديل مستقبلية.
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExamSolutionResponse,
                    # HIGH مشان نعطي الموديل أقصى مساحة تفكير ممكنة قبل
                    # ما يحسم الجواب - أهم عامل واحد بيرفع دقة حل أسئلة
                    # أكاديمية متخصصة، أياً كانت المادة (طب، هندسة، حقوق...).
                    thinking_config=types.ThinkingConfig(thinking_level=_THINKING_LEVEL),
                ),
            )

            data: ExamSolutionResponse = response.parsed
            logger.info(f"Successfully solved with {model_name} (found {len(data.solutions)} questions)")
            return data

        except Exception as e:
            logger.warning(f"Model {model_name} failed or timed out. Error: {str(e)}")
            last_exception = e
            continue

    logger.error("All AI models in the fallback chain failed.")
    raise RuntimeError(f"فشلت جميع نماذج الذكاء الاصطناعي في الاستجابة: {str(last_exception)}")


class AIService:
    @staticmethod
    async def solve_mcq_image(image_bytes: bytes) -> list[SolvedQuestion]:
        """حل صورة وحدة (استخدام المستخدمين العاديين اللي عم يبعتوا صورة)."""
        key_index, client = _get_next_client()
        data = await _call_gemini(
            contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), _SINGLE_PROMPT],
            key_index=key_index,
            client=client,
        )
        return data.solutions

    @staticmethod
    async def solve_mcq_batch(images: list[bytes]) -> dict[int, list[SolvedQuestion]]:
        """حل عدة صفحات (صور) بنداء Gemini واحد بدل نداء لكل صفحة، مشان
        نوفّر كوتا يومية كتير (RPD محدود جداً بالخطة المجانية). بيرجع
        قاموس {page_index داخل الدفعة: قائمة الأسئلة المحلولة}."""
        parts: list = [_batch_prompt(len(images))]
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))

        key_index, client = _get_next_client()
        data = await _call_gemini(contents=parts, key_index=key_index, client=client)

        grouped: dict[int, list[SolvedQuestion]] = {i: [] for i in range(len(images))}
        for sol in data.solutions:
            grouped.setdefault(sol.page_index, []).append(sol)
        return grouped
