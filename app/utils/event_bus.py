"""事件总线（支撑 SSE 实时预览）
设计：SSE 订阅端基于 logger 内存日志做“增量推送”。
- logger.add_log() 在新增日志时调用 notify_log_updated() 唤醒所有长连接
- 每个 SSE 连接持有一个游标，唤醒后从游标处取增量日志推送
- Redis 可用时可额外走 Pub/Sub 广播，供多 worker/多实例场景（预留，当前单进程已够用）
"""
import asyncio

# 日志更新的唤醒信号（进程内广播给所有等待的 SSE 任务）
_updated = asyncio.Event()

# 正在等待的连接数（用于决定是否需要常驻 Event）
_waiters = 0
_lock = asyncio.Lock()


def notify_log_updated():
    """日志更新通知（同步调用，安全）"""
    try:
        _updated.set()
    except Exception:
        pass


async def wait_log_update(timeout: float = 15.0) -> bool:
    """等待新的日志产生；返回 True=有更新，False=超时（用于 SSE 心跳保活）"""
    try:
        _updated.clear()
        await asyncio.wait_for(_updated.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
    except Exception:
        return False
