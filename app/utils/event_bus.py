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


async def wait_log_update(timeout: float = 15.0, stop_event: asyncio.Event = None) -> str:
    """等待新日志或停止信号。

    返回：
      "update" - 有新日志产生
      "stop"   - 收到 stop_event（服务关闭，SSE 应主动结束连接）
      "timeout"- 超时（用于 SSE 心跳保活）
    """
    # 若更新信号已置位（在本次 wait 之前产生），直接消费并返回，避免被误清
    if _updated.is_set():
        _updated.clear()
        return "update"
    tasks = [asyncio.create_task(_updated.wait())]
    if stop_event is not None:
        tasks.append(asyncio.create_task(stop_event.wait()))
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=timeout)
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    if stop_event is not None and stop_event.is_set():
        return "stop"
    if _updated.is_set():
        _updated.clear()
        return "update"
    return "timeout"
