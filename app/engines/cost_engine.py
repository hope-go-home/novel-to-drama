"""成本控制与配额引擎
- 按调用类型计费（LLM token / 生图张数 / 视频秒数 / TTS 字符）
- Redis 原子记账（INCR + 每日 TTL），跨 worker 安全
- 预算检查：入口拦截 + 生成前判断，避免无上限烧 API
- Redis 不可用时降级为进程内内存计数（单进程开发场景够用）
"""
import time
from datetime import date
from ..config import DAILY_BUDGET, COST_TABLE
from ..utils.redis_client import get_redis

# 内存兜底（Redis 不可用）
_memory_ledger: dict[str, float] = {}
_memory_lock = None


def _date_key(project_id: str) -> str:
    today = date.today().isoformat()
    return f"ntd:cost:{today}:{project_id}"


def estimate_cost(step: str, unit: float) -> float:
    """根据步骤类型与用量估算成本（元）"""
    if step == "script":
        # unit = 千 token 数
        return round(unit * COST_TABLE["script_per_1k_tokens"], 4)
    if step == "characters" or step == "shots":
        # unit = 张数
        return round(unit * COST_TABLE["image_per_image"], 4)
    if step == "video":
        # unit = 秒数
        return round(unit * COST_TABLE["video_per_second"], 4)
    if step == "audio":
        # unit = 千字符数
        return round(unit * COST_TABLE["tts_per_1k_chars"], 4)
    return 0.0


async def record_cost(project_id: str, step: str, amount: float) -> float:
    """记录某项目花费，返回累计金额（元）"""
    key = _date_key(project_id)
    cents = int(round(amount * 100))  # 用“分”做原子计数，避免浮点误差
    r = await get_redis()
    if r is not None:
        try:
            total_cents = await r.incrby(key, cents)
            await r.expire(key, 86400)  # 每日 TTL
            return total_cents / 100.0
        except Exception:
            pass
    # 内存降级
    _memory_ledger[key] = _memory_ledger.get(key, 0.0) + amount
    return _memory_ledger[key]


async def get_project_spend(project_id: str) -> float:
    """查询项目当日累计花费"""
    key = _date_key(project_id)
    r = await get_redis()
    if r is not None:
        try:
            cents = int(await r.get(key) or 0)
            return cents / 100.0
        except Exception:
            pass
    return _memory_ledger.get(key, 0.0)


async def check_budget(project_id: str, step: str, unit: float) -> tuple[bool, str]:
    """生成前预算检查。返回 (是否允许, 提示信息)
    估算本次 cost + 已花费 <= 预算才允许；超限不硬性阻止，由上层弹窗询问用户是否继续。
    """
    cost = estimate_cost(step, unit)
    spent = await get_project_spend(project_id)
    if spent + cost > DAILY_BUDGET:
        hint = (f"今日已花 ¥{spent:.2f}，本次「{step}」预计 ¥{cost:.2f}，"
                f"将超过每日限额 ¥{DAILY_BUDGET:.2f}。")
        return False, hint
    return True, ""
