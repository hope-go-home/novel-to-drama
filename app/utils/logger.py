"""日志管理模块"""
import json
import logging
from pathlib import Path
from datetime import datetime
from ..config import OUTPUT_DIR

# JSON 日志文件（前端展示用）
LOG_JSON_FILE = OUTPUT_DIR.parent / "logs.json"

# 文本日志文件（排查问题用）
LOG_TEXT_FILE = OUTPUT_DIR.parent / "app.log"

# 配置文本日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_TEXT_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("novel-to-drama")

# 内存日志缓存
_logs = []
MAX_LOGS = 500


def add_log(level: str, module: str, message: str, project_id: str = "", detail: str = ""):
    """添加日志"""
    log = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "module": module,
        "message": message,
        "project_id": project_id,
        "detail": detail[:500] if detail else "",
    }
    _logs.append(log)

    if len(_logs) > MAX_LOGS:
        _logs.pop(0)

    # 写入 JSON 文件（前端用）
    try:
        LOG_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_JSON_FILE.write_text(json.dumps(_logs, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

    # 写入文本日志文件（排查用）
    log_line = f"[{level}] [{module}] {message}"
    if project_id:
        log_line = f"[{level}] [{module}] [{project_id}] {message}"
    if detail:
        log_line += f" | {detail[:200]}"

    if level == "ERROR":
        logger.error(log_line)
    elif level == "WARN":
        logger.warning(log_line)
    elif level == "SUCCESS":
        logger.info(log_line)
    else:
        logger.info(log_line)


def get_logs(limit: int = 100, project_id: str = "") -> list:
    """获取日志"""
    if project_id:
        filtered = [l for l in _logs if l.get("project_id") == project_id]
    else:
        filtered = _logs
    return filtered[-limit:]


def clear_logs():
    """清空日志"""
    _logs.clear()
    if LOG_JSON_FILE.exists():
        LOG_JSON_FILE.unlink()
