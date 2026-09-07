"""文件操作工具"""
import json
from pathlib import Path


def save_json(data: dict, path: Path):
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_json(path: Path) -> dict:
    """加载 JSON 文件"""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_file_size_mb(path: str) -> float:
    """获取文件大小(MB)"""
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0
