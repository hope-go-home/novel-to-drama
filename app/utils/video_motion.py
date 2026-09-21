"""画面运动分析 - 本地 ffmpeg 抽帧计算运动能量，用于把音效对齐到画面动作时刻。

思路：
- 以低帧率、小尺寸、中心裁剪输出灰度裸流（避开运镜边缘），逐帧求平均绝对差分 = 运动能量
- 找局部显著峰值 = 画面"动作"发生的时刻
- 把音效 start 吸附到窗口内最近的峰值（峰不显著就不动）

不依赖 numpy，纯 Python 计算；同一片段按 mtime 缓存，避免重复分析。
"""
import subprocess
from pathlib import Path

from .ffmpeg_utils import FFMPEG_PATH

_CURVE_CACHE = {}


def motion_curve(video_path, fps: int = 10, w: int = 160, h: int = 90, crop_ratio: float = 0.6) -> list:
    """返回 [(t, energy)]，energy 已归一到 0~1（平均每像素绝对差分 / 255）。"""
    p = Path(video_path)
    if not p.exists():
        return []
    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = 0
    ck = (str(p), mtime, fps, w, h, crop_ratio)
    if ck in _CURVE_CACHE:
        return _CURVE_CACHE[ck]

    vf = f"fps={fps},crop=iw*{crop_ratio}:ih*{crop_ratio},scale={w}:{h},format=gray"
    cmd = [
        FFMPEG_PATH, "-v", "error", "-i", str(p),
        "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception:
        return []
    if r.returncode != 0 or not r.stdout:
        return []

    data = r.stdout
    fsize = w * h
    n = len(data) // fsize
    if n < 2:
        return []

    curve = []
    prev = data[0:fsize]
    for i in range(1, n):
        cur = data[i * fsize:(i + 1) * fsize]
        s = 0
        for a, b in zip(prev, cur):
            d = b - a
            s += d if d >= 0 else -d
        curve.append((i / float(fps), (s / fsize) / 255.0))
        prev = cur
    _CURVE_CACHE[ck] = curve
    return curve


def find_peaks(curve: list, min_gap: float = 0.3, k: float = 0.6) -> list:
    """找显著运动峰值。返回 [(t, energy)]，按时间升序。
    阈值 = max(0.02, 均值 + k*标准差)，滤掉持续的运镜/噪声，只保留明显凸起。
    """
    if not curve or len(curve) < 3:
        return []
    energies = [e for _, e in curve]
    times = [t for t, _ in curve]
    n = len(energies)
    mean = sum(energies) / n
    var = sum((x - mean) ** 2 for x in energies) / n
    std = var ** 0.5
    thr = max(0.02, mean + k * std)

    cand = []
    for i in range(1, n - 1):
        e = energies[i]
        if e >= energies[i - 1] and e >= energies[i + 1] and e >= thr:
            cand.append((times[i], e))
    if not cand:
        return []

    cand.sort(key=lambda x: -x[1])
    kept = []
    for t, e in cand:
        if all(abs(t - kt) >= min_gap for kt, _ in kept):
            kept.append((t, e))
    kept.sort(key=lambda x: x[0])
    return kept


def align_starts(starts: list, peaks: list, window: float = 0.6) -> list:
    """把每个 start 吸附到 window 内最近的、未被占用的峰值；找不到则保持原值。
    保持与输入相同的顺序与个数。
    """
    if not peaks or not starts:
        return list(starts)
    peak_ts = [t for t, _ in peaks]
    used = set()
    out = []
    for s in starts:
        best_idx, best_d = None, None
        for idx, t in enumerate(peak_ts):
            if idx in used:
                continue
            d = abs(t - s)
            if d <= window and (best_d is None or d < best_d):
                best_idx, best_d = idx, d
        if best_idx is not None:
            used.add(best_idx)
            out.append(max(0.0, peak_ts[best_idx]))
        else:
            out.append(s)
    return out
