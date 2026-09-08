"""剧本校验与时长预检（AI 剧本助手 / 语音生成前共用同一套约束）

约束集：
- 单镜"对白+旁白"朗读字数上限（按实测 ~5字/s，预留余量）
- 单镜预计朗读时长 ≤ SHOT_MAX_SEC
- 剧本结构完整性（场景/镜头/角色存在、字段可解析）
"""
from ..config import SHOT_MAX_SEC, SHOT_MAX_CHARS

# 朗读速度估算：SHOT_MAX_CHARS 个字须在 SHOT_MAX_SEC 秒内读完 → 字/秒
# 实测模型约 5~6 字/s；此处由上限反推，保证"字数达标即时长达标"
CHARS_PER_SEC = float(SHOT_MAX_CHARS / max(SHOT_MAX_SEC, 1))


def count_readable_chars(shot: dict) -> int:
    """统计一个镜头的可朗读字数 = 对白台词 + 旁白"""
    n = 0
    for d in (shot.get("dialogues") or []):
        if isinstance(d, dict):
            n += len((d.get("line") or "").strip())
    n += len((shot.get("narrator") or "").strip())
    return n


def estimate_shot_seconds(shot: dict) -> float:
    """估算单镜朗读时长（秒）"""
    return round(count_readable_chars(shot) / CHARS_PER_SEC, 1)


def flat_shots(script: dict) -> list:
    """把剧本拍平为 (scene_idx, scene, shot) 列表"""
    out = []
    for si, scene in enumerate(script.get("scenes") or []):
        for shot in scene.get("shots") or []:
            out.append((si, scene, shot))
    return out


def validate_script(script: dict) -> dict:
    """校验剧本。返回 {ok, errors[], warnings[], shots[]}

    errors: 结构性问题（阻止应用）
    warnings: 超长镜头（可应用但建议处理）
    shots:  每镜时长信息（供前端表格）
    """
    errors, warnings, shots = [], [], []

    if not isinstance(script, dict):
        errors.append("剧本不是有效对象")
        return {"ok": False, "errors": errors, "warnings": warnings, "shots": shots}

    if not script.get("title"):
        errors.append("缺少标题 title")

    scenes = script.get("scenes")
    if not isinstance(scenes, list) or len(scenes) == 0:
        errors.append("缺少场景 scenes（至少 1 个）")
    else:
        total_shots = 0
        for si, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                errors.append(f"场景 {si} 格式错误")
                continue
            shot_list = scene.get("shots")
            if not isinstance(shot_list, list) or len(shot_list) == 0:
                errors.append(f"场景 {si + 1} 缺少镜头 shots")
                continue
            total_shots += len(shot_list)

        if total_shots == 0:
            errors.append("没有任何镜头")

    # 逐镜头时长预检
    for si, scene, shot in flat_shots(script):
        chars = count_readable_chars(shot)
        secs = estimate_shot_seconds(shot)
        num = shot.get("shot_number", "")
        loc = scene.get("location", "")
        shots.append({
            "scene": si + 1,
            "shot": num,
            "location": loc,
            "chars": chars,
            "seconds": secs,
            "over": secs > SHOT_MAX_SEC,
        })
        if secs > SHOT_MAX_SEC:
            warnings.append(
                f"场景{si + 1} 镜头{num} 可朗读 {chars} 字 ≈ {secs}s，"
                f"超上限 {SHOT_MAX_SEC}s，可能超出视频模型单镜时长，建议精简或拆分"
            )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "shots": shots,
    }


def summarize_script(script: dict) -> dict:
    """生成剧本摘要（供前端对比：标题/角色/场景/镜头数/总朗读字数）"""
    scenes = script.get("scenes") or []
    shots = flat_shots(script)
    chars = sum(count_readable_chars(s) for _, _, s in shots)
    return {
        "title": script.get("title", ""),
        "characters": len(script.get("characters") or []),
        "scenes": len(scenes),
        "shots": len(shots),
        "total_chars": chars,
    }
