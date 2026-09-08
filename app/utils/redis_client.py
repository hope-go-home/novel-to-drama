"""Redis 客户端封装
- 连接 ntd-redis（宿主端口 6381）
- Redis 不可用 / 未安装 redis 库时自动降级为空操作，不阻塞主流程
"""
import asyncio
import logging
from ..config import REDIS_URL

logger = logging.getLogger("novel-to-drama")

# 全局客户端（懒加载）
_redis = None
_redis_available: bool | None = None  # None=未探测


async def get_redis():
    """获取 Redis 客户端（不存在则创建）；不可用时返回 None"""
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        await _redis.ping()
        _redis_available = True
        logger.info(f"Redis 连接成功: {REDIS_URL}")
        return _redis
    except Exception as e:
        _redis_available = False
        _redis = None
        logger.warning(f"Redis 不可用，降级为无缓存模式: {e}")
        return None


async def redis_set(key: str, value: str, ttl: int = None):
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(key, value, ex=ttl)
    except Exception:
        pass


async def redis_get(key: str) -> str | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        return await r.get(key)
    except Exception:
        return None


async def redis_incr(key: str, amount: int = 1, ttl: int = None) -> int:
    """原子自增；Redis 不可用时返回 0（调用方按 0 计费即可，纯内存兜底）"""
    r = await get_redis()
    if r is None:
        return 0
    try:
        val = await r.incrby(key, amount)
        if ttl:
            await r.expire(key, ttl)
        return val
    except Exception:
        return 0


async def redis_publish(channel: str, message: str):
    r = await get_redis()
    if r is None:
        return
    try:
        await r.publish(channel, message)
    except Exception:
        pass


async def redis_pubsub_listener(channel: str):
    """异步订阅频道，yield (channel, message)；Redis 不可用时立即结束"""
    r = await get_redis()
    if r is None:
        return
    try:
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message and message.get("type") == "message":
                yield message["data"]
    except Exception:
        return
