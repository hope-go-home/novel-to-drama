"""AI 视频生成引擎 - 分镜画面 → 动态视频片段
使用阿里云 DashScope 万相 Wan2.7 (wan2.7-r2v) 参考图生视频 API
"""
import httpx
import asyncio
import base64
import json
import subprocess
from pathlib import Path
from ..config import DASHSCOPE_API_KEY, VIDEO_API_BASE, VIDEO_MODEL, VIDEO_DURATION
from ..models import Shot
from ..utils.logger import add_log

VIDEO_SYNTH_URL = f"{VIDEO_API_BASE}/api/v1/services/aigc/video-generation/video-synthesis"
TASK_QUERY_URL = f"{VIDEO_API_BASE}/api/v1/tasks"


def resolve_media_type() -> str:
    """根据模型选择首帧图参数类型。
    - r2v（reference-image-to-video，如 wan2.7-r2v / happyhorse-1.1-r2v）→ reference_image
    - 其余首帧生成模型（i2v / wan 图生视频）→ first_frame
    """
    m = (VIDEO_MODEL or "").lower()
    if "r2v" in m:
        return "reference_image"
    return "first_frame"


def _get_media_duration(media_path: str) -> float:
    """获取音视频文件时长（秒）；缺失/失败返回 0.0（统一委托 ffmpeg_utils）"""
    from ..utils.ffmpeg_utils import probe_duration
    return probe_duration(media_path)


def build_video_prompt(shot: Shot, use_tts: bool = True) -> str:
    """构建视频生成 prompt（用场景图作首帧，注入台词/情绪/动作，并保证角色形象一致）

    use_tts=True （TTS 配音模式）：画面做无声口型，禁止自带人声，对白由后期 TTS 提供
    use_tts=False（AI 原声模式）：要求角色真实发声说出台词，保留视频自带对白/环境声
    """
    parts = []
    # 参考图指代
    parts.append("Based on the scene in Image 1")

    if shot.video_prompt:
        parts.append(shot.video_prompt)
    elif shot.description:
        parts.append(shot.description)

    # 台词/动作注入 + 角色一致性提示
    lines = shot.dialogues or []
    has_speech = any(d.line.strip() for d in lines)
    if has_speech:
        parts.append("Keep every character's appearance exactly identical to their established look in previous scenes")
        for d in lines:
            if d.line.strip():
                line = d.line.strip()
                emotion = d.emotion or "平静"
                action = f", {d.action.strip()}" if d.action and d.action.strip() else ""
                if use_tts:
                    # TTS 模式：无声对口型，人声由后期配音
                    parts.append(
                        f'Character {d.character} mouths the line silently: "{line}" '
                        f"with a {emotion} facial expression and lip movement only{action}"
                    )
                else:
                    # 原声模式：角色要真实发声说出台词（成片直接使用视频自带人声）
                    parts.append(
                        f'Character {d.character} says aloud the line: "{line}" '
                        f"with a {emotion} tone of voice and natural speech{action}"
                    )
        if use_tts:
            # TTS 模式对白由后期配音提供，禁止视频自带任何人声/朗读声
            parts.append(
                "The dialogue is dubbed later; generate NO audible speech, no vocals, "
                "no English or any language narration audio, no mouthing sounds. "
                "Audio track (if any) should contain only ambient/environmental sound effects such as wind, footsteps or background noise."
            )
    elif shot.narrator and shot.narrator.strip() and use_tts:
        parts.append(
            "No character speaks aloud or mouths anything; this scene is silent, "
            "its narration is added later as voice-over. "
            "Audio track (if any) should contain only ambient/environmental sound effects, no speech or vocals."
        )

    camera_map = {
        "推": "slow zoom in",
        "拉": "slow zoom out",
        "摇": "pan left to right",
        "移": "smooth lateral movement",
        "固定": "static camera, subtle natural movement",
    }
    parts.append(camera_map.get(shot.camera, "static camera, subtle natural movement"))

    return ", ".join(parts)


async def _generate_video_clip(
    image_path: str,
    prompt: str,
    duration: int,
    output_path: Path,
) -> str:
    """调用 DashScope wan2.7-r2v 图生视频"""
    if not DASHSCOPE_API_KEY:
        raise ValueError("未配置 DASHSCOPE_API_KEY")

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    # 图片转 base64 data URI 作为首帧
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode()
    data_uri = f"data:image/png;base64,{image_base64}"

    payload = {
        "model": VIDEO_MODEL,
        "input": {
            "prompt": prompt,
            "media": [
                {"type": resolve_media_type(), "url": data_uri}
            ],
        },
        "parameters": {
            "resolution": "720P",
            "duration": max(2, int(duration)),
            "ratio": "16:9",
            "prompt_extend": False,
            "watermark": False,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 提交任务
        response = await client.post(
            VIDEO_SYNTH_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        task_data = response.json()

        task_id = task_data.get("output", {}).get("task_id")
        if not task_id:
            raise ValueError(f"视频任务创建失败: {task_data}")

        print(f"  视频任务已创建: {task_id}")

        # 轮询等待结果，不设超时，等到完成为止
        attempt = 0
        while True:
            await asyncio.sleep(5)
            attempt += 1

            status_resp = await client.get(
                f"{TASK_QUERY_URL}/{task_id}",
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            )
            status_data = status_resp.json()
            output = status_data.get("output", {})
            status = output.get("task_status", "")

            if status == "SUCCEEDED":
                video_url = output.get("video_url")
                if not video_url:
                    results = output.get("results", [])
                    if results:
                        video_url = results[0].get("url") or results[0].get("video_url")
                if not video_url:
                    raise ValueError(f"任务成功但未找到视频URL: {status_data}")

                # 下载视频
                video_resp = await client.get(video_url)
                video_resp.raise_for_status()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(video_resp.content)
                return str(output_path)

            elif status == "FAILED":
                error_msg = output.get("message", "未知错误")
                raise ValueError(f"视频生成失败: {error_msg}")

            if attempt % 6 == 0:  # 每30秒打印一次
                print(f"  等待中... 状态: {status} ({attempt * 5}s)")


async def generate_video_clips(
    shots: list[Shot],
    shot_image_paths: list[str],
    project_dir: Path,
    project_id: str = "",
    audio_paths: list = None,
    use_tts: bool = True,
) -> list[str]:
    """为所有分镜生成 AI 视频片段（每完成一个即增量写 video_paths.json，供前端实时展示）"""
    clips_dir = project_dir / "video_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    index_path = project_dir / "video_paths.json"
    total = len(shots)

    def _flush(indexes: list):
        """把当前已完成结果落盘为与镜头数等长的数组（未生成的位置为 null）"""
        padded = list(indexes) + [None] * (total - len(indexes))
        try:
            index_path.write_text(
                json.dumps(padded, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"video_paths 增量写入失败: {e}")

    results = []
    for i, (shot, image_path) in enumerate(zip(shots, shot_image_paths)):
        if not image_path:
            results.append(None)
            _flush(results)
            continue

        output_path = clips_dir / f"clip_{i:04d}.mp4"

        # 检查视频是否已存在，存在则跳过生成
        if output_path.exists():
            add_log("INFO", "video", f"分镜 {i} 视频已存在，跳过生成", project_id, str(output_path))
            results.append(str(output_path))
            _flush(results)
            continue

        # 计算视频时长：有配音则 = max(镜头基础时长, 对白+旁白总时长)，与合成对齐；无配音 4-6 秒
        import random
        dialogue_dur = 0.0
        narrator_dur = 0.0
        if audio_paths and i < len(audio_paths):
            audio_info = audio_paths[i] or {}
            d = audio_info.get("dialogue_audio")
            n = audio_info.get("narrator_audio")
            if d:
                dialogue_dur = _get_media_duration(d)
            if n:
                narrator_dur = _get_media_duration(n)

        voice_total = dialogue_dur + narrator_dur
        if voice_total > 0:
            duration = int(max(float(shot.duration or 3.0), voice_total))
        else:
            duration = random.randint(4, 6)

        # 单镜视频硬上限 10 秒；更长的配音/旁白在合成阶段用冻结末帧延展
        duration = max(2, min(duration, 10))

        prompt = build_video_prompt(shot, use_tts=use_tts)

        try:
            add_log("INFO", "video", f"开始生成分镜 {i} 视频（{duration}秒）", project_id)
            result = await _generate_video_clip(
                image_path=image_path,
                prompt=prompt,
                duration=duration,
                output_path=output_path,
            )
            results.append(result)
            add_log("SUCCESS", "video", f"分镜 {i} 视频完成", project_id)
        except Exception as e:
            add_log("ERROR", "video", f"分镜 {i} 视频生成失败", project_id, str(e))
            results.append(None)

        _flush(results)
        await asyncio.sleep(1)

    return results
