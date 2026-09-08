"""FFmpeg 工具 - 视频理解层
提供：媒体时长探测、音轨探测、抽帧（用于质量评估/预览）
复用 imageio-ffmpeg 内置二进制，无需额外安装。
"""
import subprocess
from pathlib import Path

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = "ffmpeg"


def _resolve_path(media_path: str, base_dir: str = None) -> Path:
    """解析媒体路径：若为相对路径且原位置不存在，则尝试相对 base_dir 拼接"""
    p = Path(media_path)
    if p.exists():
        return p
    if base_dir and not p.is_absolute():
        cand = Path(base_dir) / p
        if cand.exists():
            return cand
    return p


def probe_duration(media_path: str, base_dir: str = None) -> float:
    """获取音视频文件时长（秒）；失败/缺失返回 0.0"""
    p = _resolve_path(media_path, base_dir)
    if not p.exists():
        return 0.0
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", str(p)],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stderr.split('\n'):
            if 'Duration:' in line:
                d = line.split('Duration:')[1].split(',')[0].strip()
                parts = d.split(':')
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return 0.0
    except Exception:
        return 0.0


def probe_has_audio(media_path: str, base_dir: str = None) -> bool:
    """判断媒体文件是否带音轨"""
    p = _resolve_path(media_path, base_dir)
    if not p.exists():
        return False
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", str(p)],
            capture_output=True, text=True, timeout=10,
        )
        return any("Audio:" in line for line in result.stderr.split('\n'))
    except Exception:
        return False


def extract_frame(video_path: str, output_path: str, at_second: float = 0.0) -> str | None:
    """从视频抽一帧保存为图片，返回输出路径；失败返回 None"""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            FFMPEG_PATH, "-y",
            "-ss", str(at_second),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not Path(output_path).exists():
            return None
        return str(output_path)
    except Exception:
        return None
