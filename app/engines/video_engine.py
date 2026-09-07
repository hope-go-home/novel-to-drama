"""AI 视频生成引擎 - 分镜画面 → 动态视频片段
使用阿里云 DashScope 万相 Wan2.7 (wan2.7-r2v) 参考图生视频 API
"""
import httpx
import asyncio
import base64
import subprocess
from pathlib import Path
from ..config import DASHSCOPE_API_KEY, VIDEO_API_BASE, VIDEO_MODEL, VIDEO_DURATION
from ..models import Shot
from ..utils.logger import add_log

VIDEO_SYNTH_URL = f"{VIDEO_API_BASE}/api/v1/services/aigc/video-generation/video-synthesis"
TASK_QUERY_URL = f"{VIDEO_API_BASE}/api/v1/tasks"


# 使用 imageio-ffmpeg 内置的 FFmpeg
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = "ffmpeg"


def _get_media_duration(media_path: str) -> float:
    """获取音视频文件时长"""
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", media_path],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stderr.split('\n'):
            if 'Duration:' in line:
                duration_str = line.split('Duration:')[1].split(',')[0].strip()
                parts = duration_str.split(':')
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        return 3.0
    except Exception:
        return 3.0


def build_video_prompt(shot: Shot) -> str:
    """构建视频生成 prompt（wan2.7-r2v 用参考图，prompt 用 Image 1 指代参考图）"""
    parts = []
    # 参考图指代
    parts.append("Based on the scene in Image 1")

    if shot.video_prompt:
        parts.append(shot.video_prompt)
    else:
        parts.append(shot.description)

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
                {"type": "reference_image", "url": data_uri}
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
) -> list[str]:
    """为所有分镜生成 AI 视频片段"""
    clips_dir = project_dir / "video_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, (shot, image_path) in enumerate(zip(shots, shot_image_paths)):
        if not image_path:
            results.append(None)
            continue

        output_path = clips_dir / f"clip_{i:04d}.mp4"

        # 检查视频是否已存在，存在则跳过生成
        if output_path.exists():
            add_log("INFO", "video", f"分镜 {i} 视频已存在，跳过生成", project_id, str(output_path))
            results.append(str(output_path))
            continue

        # 计算视频时长：根据配音时长，无配音则4-6秒
        import random
        audio_duration = 0.0
        if audio_paths and i < len(audio_paths):
            audio_info = audio_paths[i]
            d = audio_info.get("dialogue_audio")
            n = audio_info.get("narrator_audio")
            if d:
                audio_duration = max(audio_duration, _get_media_duration(d))
            if n:
                audio_duration = max(audio_duration, _get_media_duration(n))

        if audio_duration > 0:
            duration = int(audio_duration)
        else:
            duration = random.randint(4, 6)

        prompt = build_video_prompt(shot)

        try:
            add_log("INFO", "video", f"开始生成分镜 {i} 视频（{duration}秒）", project_id)
            result = await _generate_video_clip(
                image_path=image_path,
                prompt=prompt,
                duration=int(audio_duration),
                output_path=output_path,
            )
            results.append(result)
            add_log("SUCCESS", "video", f"分镜 {i} 视频完成", project_id)
        except Exception as e:
            add_log("ERROR", "video", f"分镜 {i} 视频生成失败", project_id, str(e))
            results.append(None)

        await asyncio.sleep(1)

    return results
