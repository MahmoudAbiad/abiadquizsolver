from datetime import datetime
import redis.asyncio as redis
from config.settings import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

class RedisService:
    @staticmethod
    def _get_key(user_id: int) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"free_quota:{user_id}:{today}"

    @classmethod
    async def get_remaining_free_quota(cls, user_id: int) -> int:
        key = cls._get_key(user_id)
        used = await redis_client.get(key)
        used_count = int(used) if used else 0
        return max(0, settings.FREE_DAILY_LIMIT - used_count)

    @classmethod
    async def increment_free_usage(cls, user_id: int):
        key = cls._get_key(user_id)
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        await pipe.execute()
