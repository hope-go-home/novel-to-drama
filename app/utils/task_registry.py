"""任务注册表
- 将生成任务状态从进程内内存 dict 迁移到 Redis 持久化（key: ntd:task:{project_id}）
- Redis 不可用时降级为进程内内存表，不破坏原行为
- 为后续多 worker / Celery 扩展铺路
"""
import json
import time
from ..utils.redis_client import get_redis

TASK_TTL = 86400  # 任务记录保留 24h

# 内存兜底（Redis 不可用时的降级存储）
_memory_tasks: dict[str, dict] = {}


def _key(project_id: str) -> str:
    return f"ntd:task:{project_id}"


async def set_task(project_id: str, step: str, status: str, message: str = "") -> None:
    """记录/更新某项目的任务状态"""
    record = {
        "project_id": project_id,
        "step": step,
        "status": status,          # running / done / error / cancelled
        "message": message,
        "started_at": time.time(),
        "updated_at": time.time(),
    }
    r = await get_redis()
    if r is not None:
        try:
            await r.set(_key(project_id), json.dumps(record), ex=TASK_TTL)
            return
        except Exception:
            pass
    _memory_tasks[project_id] = record


async def get_task(project_id: str) -> dict | None:
    r = await get_redis()
    if r is not None:
        try:
            raw = await r.get(_key(project_id))
            if raw:
                return json.loads(raw)
            return None
        except Exception:
            pass
    return _memory_tasks.get(project_id)


async def clear_task(project_id: str) -> None:
    r = await get_redis()
    if r is not None:
        try:
            await r.delete(_key(project_id))
        except Exception:
            pass
    _memory_tasks.pop(project_id, None)
