import asyncio
from datetime import datetime
import redis.asyncio as redis
from config.settings import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


class GeminiQuotaService:
    """تتبّع استهلاك كل مفتاح Gemini API من حد الـ RPD (طلبات باليوم) على
    الخطة المجانية. هاد طبقة حماية إضافية: بتمنع البوت إنو يبلش شغلة كبيرة
    (متل ملف 60 صفحة) وهو أصلاً ما رح يقدر يكملها لأن الكوتا اليومية
    خلصت، وبتحافظ على جزء من الكوتا لباقي المستخدمين بدل ما يوكلها كلها
    ملف واحد."""

    @staticmethod
    def _key(key_index: int) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"gemini_quota:{key_index}:{today}"

    @classmethod
    async def get_remaining(cls, key_index: int) -> int:
        used = await redis_client.get(cls._key(key_index))
        used_count = int(used) if used else 0
        return max(0, settings.GEMINI_DAILY_LIMIT_PER_KEY - used_count)

    @classmethod
    async def get_total_remaining(cls, num_keys: int) -> int:
        """مجموع الكوتا المتبقية اليوم عبر كل المفاتيح مجتمعة."""
        remaining_per_key = await asyncio.gather(
            *(cls.get_remaining(i) for i in range(num_keys))
        )
        return sum(remaining_per_key)

    @classmethod
    async def increment(cls, key_index: int):
        """بتنادى مرة وحدة لكل نداء فعلي بيروح لـ Gemini (مو لكل صفحة —
        النداء الواحد ممكن يغطي عدة صفحات دفعة وحدة عن طريق الـ batching)."""
        key = cls._key(key_index)
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        await pipe.execute()
