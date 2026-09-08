"""质量评估引擎 - 对生成的分镜画面做质量闸门检查
两层评估（纯本地、免费、无外部 API 依赖）：
1. 文件层：存在 / 非空 / 可解码 / 尺寸合理
2. 图像启发式：模糊度(方差近似) / 亮度异常（Pillow）

结果写入 shot_quality.json，供前端展示；低质画面可被阻止进入高成本视频环节。
"""
from datetime import datetime
from typing import Optional

from ..models import Shot, ShotQuality

FUZZY_THRESHOLD = 30.0   # Laplacian 方差低于此值视为可能模糊（近似经验值）
LOW_SCORE = 50.0         # 低于该综合分标记为 low
MED_SCORE = 70.0         # 低于该综合分标记为 medium


def _assess_file(path: str) -> dict:
    """文件层检查"""
    from pathlib import Path
    from ..utils.file_utils import get_file_size_mb
    p = Path(path)
    checks = {}
    if not p.exists():
        return {"passed": False, "reason": "文件不存在"}
    checks["exists"] = True
    size_mb = get_file_size_mb(path)
    checks["size_mb"] = round(size_mb, 2)
    if size_mb <= 0:
        return {"passed": False, "reason": "文件为空(0字节)"}
    checks["size_ok"] = True
    return {"passed": True, "checks": checks}


def _assess_image_heuristics(path: str) -> dict:
    """图像启发式：模糊 / 亮度异常（近似实现，不依赖 numpy）"""
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"passed": True, "checks": {}, "score": 100.0, "skipped": True}

    try:
        img = Image.open(path)
        img.load()
        width, height = img.size
        checks = {"width": width, "height": height}
        score = 100.0
        reason = ""

        # 尺寸合理
        if width < 320 or height < 180:
            score = min(score, 30.0)
            reason += "尺寸过小; "

        # 转灰度缩小后用方差近似判断模糊
        small = img.convert("L").resize((64, 48))
        # Laplacian 近似的实现：中心像素与四邻域差
        laplacian_var = _laplacian_variance(small)
        checks["laplacian_var"] = round(laplacian_var, 2)
        if laplacian_var < FUZZY_THRESHOLD * 0.05:
            score = min(score, 30.0)
            reason += "画面可能模糊; "

        # 亮度：均值离 128 太远视为过曝/欠曝
        stat = ImageStat.Stat(img.convert("L"))
        mean_l = stat.mean[0]
        checks["mean_luminance"] = round(mean_l, 1)
        if mean_l > 235:
            score = min(score, 60.0)
            reason += "疑似过曝; "
        elif mean_l < 20:
            score = min(score, 60.0)
            reason += "疑似过暗; "

        passed = score >= LOW_SCORE
        return {"passed": passed, "checks": checks, "score": round(score, 1), "reason": reason.strip("; ")}
    except Exception as e:
        return {"passed": False, "checks": {}, "score": 0.0, "reason": f"图像解码失败: {str(e)[:80]}"}


def _laplacian_variance(gray_img):
    """计算灰度图的拉普拉斯方差（近似模糊度）。越模糊值越小。"""
    px = gray_img.load()
    w, h = gray_img.size
    total = 0.0
    count = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            center = px[x, y]
            lap = (px[x - 1, y] + px[x + 1, y] + px[x, y - 1] + px[x, y + 1] - 4 * center)
            total += lap * lap
            count += 1
    if count == 0:
        return 0.0
    return total / count


async def assess_shot_image(shot: Shot, index: int, image_path: str) -> ShotQuality:
    """对单张分镜画面做两层评估（文件 + 启发式），返回聚合结果"""
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = ShotQuality(index=index, checked_at=checked_at)

    # 1. 文件层
    file_res = _assess_file(image_path)
    if not file_res.get("passed"):
        result.passed = False
        result.score = 0
        result.level = "low"
        result.reason = file_res.get("reason", "文件异常")
        result.checks = {"file": file_res}
        return result
    result.checks["file"] = file_res.get("checks", {})

    # 2. 图像启发式
    heur = _assess_image_heuristics(image_path)
    result.checks["heuristic"] = heur.get("checks", {})
    heur_score = heur.get("score", 100.0)
    result.score = heur_score
    if not heur.get("passed", True):
        result.passed = False
        result.reason = heur.get("reason", "启发式检查未通过")

    # 汇总 level
    if result.score < LOW_SCORE:
        result.level = "low"
    elif result.score < MED_SCORE:
        result.level = "medium"
    else:
        result.level = "high"
    if result.passed and result.level == "low":
        result.passed = False
    return result


async def assess_shot_images(shots: list[Shot], image_paths: list[str]) -> list[Optional[ShotQuality]]:
    """批量评估一个项目的所有分镜画面"""
    results: list[Optional[ShotQuality]] = []
    for i, shot in enumerate(shots):
        path = image_paths[i] if i < len(image_paths) else None
        if not path:
            results.append(None)
            continue
        results.append(await assess_shot_image(shot, i, path))
    return results
