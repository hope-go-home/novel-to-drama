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


def find_peaks(curve: list, min_gap: float = 0.6, top_k: int = 3, prom_ratio: float = 0.4) -> list:
    """找显著运动峰值。返回 [(t, energy)]，按时间升序。

    针对真实 AI 片段（多为持续/周期性微动 + 运镜）做了收紧：
    - 先平滑曲线，阈值取 max(0.02, 均值 + 0.8·标准差)
    - 用"显著度 prominence"（峰高出两侧基线的幅度）过滤周期性小起伏
    - 只保留最重要的 top_k 个，且两两间隔 >= min_gap
    - 找不到显著峰则返回空（调用方据此退回台词/剧本时间，宁可不吸也不吸错）
    """
    if not curve or len(curve) < 3:
        return []
    times = [t for t, _ in curve]
    raw = [e for _, e in curve]
    n = len(raw)

    # 平滑（3 点滑动平均）后统计
    sm = []
    for i in range(n):
        lo = max(0, i - 1)
        hi = min(n, i + 2)
        sm.append(sum(raw[lo:hi]) / (hi - lo))

    mean = sum(sm) / n
    mx = max(sm)
    if mx <= 1e-6:
        return []
    std = (sum((x - mean) ** 2 for x in sm) / n) ** 0.5
    thr = max(0.02, mean + 0.8 * std)
    prom_thr = max(0.015, prom_ratio * (mx - mean))

    cands = []
    for i in range(1, n - 1):
        h = sm[i]
        if h >= sm[i - 1] and h >= sm[i + 1] and h >= thr:
            l = i - 1
            lmin = h
            while l >= 0 and sm[l] <= h:
                lmin = min(lmin, sm[l])
                l -= 1
            r = i + 1
            rmin = h
            while r < n and sm[r] <= h:
                rmin = min(rmin, sm[r])
                r += 1
            prom = h - max(lmin, rmin)
            if prom >= prom_thr:
                cands.append((times[i], h, prom))

    if not cands:
        return []

    cands.sort(key=lambda x: -x[2])
    kept = []
    for t, h, _p in cands:
        if all(abs(t - kt) >= min_gap for kt, _, _ in kept):
            kept.append((t, h, _p))
        if len(kept) >= top_k:
            break
    kept.sort(key=lambda x: x[0])
    return [(t, h) for t, h, _p in kept]


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
