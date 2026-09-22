"""AI 视频生成引擎 - 分镜画面 → 动态视频片段
使用阿里云 DashScope 万相 Wan 图生视频 API（i2v 首帧 / r2v 参考图，按 VIDEO_MODEL 自动适配协议）
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


def is_i2v_model() -> bool:
    """是否为 i2v（首帧图生视频）模型（如 wan2.6-i2v / wan2.7-i2v）。
    均不支持 ratio 参数（宽高比随首帧图）。
    """
    m = (VIDEO_MODEL or "").lower()
    return "i2v" in m


def uses_new_i2v_protocol() -> bool:
    """是否为"新版图生视频协议"的 i2v 模型（wan2.7-i2v 及以后）。
    新版协议首帧放在 input.media=[{type:first_frame,url}]，不再使用 input.img_url。
    """
    m = (VIDEO_MODEL or "").lower()
    return "i2v" in m and ("2.7" in m or "3." in m)


def build_video_input(prompt: str, data_uri: str) -> dict:
    """按模型协议构造请求的 input 对象。
    - 老版 i2v（wan2.6 及更早）：首帧图放 input.img_url
    - 新版 i2v（wan2.7+）/ r2v：统一放 input.media（首帧 type=first_frame / 参考图 type=reference_image）
    """
    if is_i2v_model() and not uses_new_i2v_protocol():
        return {"prompt": prompt, "img_url": data_uri}
    return {
        "prompt": prompt,
        "media": [{"type": resolve_media_type(), "url": data_uri}],
    }


def _get_media_duration(media_path: str) -> float:
    """获取音视频文件时长（秒）；缺失/失败返回 0.0（统一委托 ffmpeg_utils）"""
    from ..utils.ffmpeg_utils import probe_duration
    return probe_duration(media_path)


def clip_filename(index: int, use_tts: bool = True) -> str:
    """视频片段文件名：TTS 模式沿用 clip_XXXX.mp4（兼容旧片段），AI 原声模式用 clip_XXXX_orig.mp4。
    两种模式各存一份，来回切换互不覆盖、无需重复生成。
    """
    return f"clip_{index:04d}.mp4" if use_tts else f"clip_{index:04d}_orig.mp4"


def video_index_filename(use_tts: bool = True) -> str:
    """视频索引文件名（每个模式各一份）"""
    return "video_paths.json" if use_tts else "video_paths_orig.json"


def build_video_prompt(shot: Shot, use_tts: bool = True) -> str:
    """构建视频生成 prompt（用场景图作首帧，注入台词/情绪/动作，并保证角色形象一致）

    use_tts=True （TTS 配音模式）：画面做无声口型，禁止自带人声，对白由后期 TTS 提供
    use_tts=False（AI 原声模式）：要求角色真实发声说出台词，保留视频自带对白/环境声
    """
    parts = []
    # 参考图指代（仅 r2v 参考图模型需要；i2v 首帧模型不传此句）
    if not is_i2v_model():
        parts.append("Based on the scene in Image 1")

    # ① 动作/镜头描述放最前面（模型注意力最高）
    if shot.video_prompt:
        parts.append(shot.video_prompt)
    elif shot.description:
        parts.append(shot.description)

    # ② 台词/动作注入（中等优先级）
    lines = shot.dialogues or []
    has_speech = any(d.line.strip() for d in lines)
    if has_speech:
        for d in lines:
            if d.line.strip():
                line = d.line.strip()
                emotion = d.emotion or "平静"
                action = f", {d.action.strip()}" if d.action and d.action.strip() else ""
                if use_tts:
                    parts.append(
                        f'Character {d.character} mouths the line silently: "{line}" '
                        f"with a {emotion} facial expression and lip movement only{action}"
                    )
                else:
                    parts.append(
                        f'Character {d.character} says aloud the line: "{line}" '
                        f"with a {emotion} tone of voice and natural speech{action}"
                    )
        parts.append("Keep every character's appearance exactly identical to their established look in previous scenes")

    # ③ 强制注入运动关键词（i2v 模型需要明确的运动指令才会做出明显动作）
    if is_i2v_model():
        motion_boost = "cinematic dynamic scene, dramatic character movement, " \
                       "expressive gestures and body language, camera motion, " \
                       "particles and environmental effects in motion"
        parts.append(motion_boost)

    # ④ TTS 禁音指令放最后（避免稀释动作描述）
    if use_tts:
        if has_speech:
            parts.append(
                "The dialogue is dubbed later; generate NO audible speech, no vocals, "
                "no narration audio. Audio track should contain only ambient/environmental sounds."
            )
        elif shot.narrator and shot.narrator.strip():
            parts.append(
                "No character speaks aloud or mouths anything; this scene is silent, "
                "its narration is added later as voice-over. "
                "Audio track should contain only ambient/environmental sounds, no speech."
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
    """调用 DashScope 万相图生视频（按 VIDEO_MODEL 自动适配 i2v 新版/老版协议）"""
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

    # 按模型能力构造 input：
    # - 老版 i2v（wan2.6-i2v 等）：首帧图放 input.img_url
    # - 新版 i2v（wan2.7-i2v 等）/ r2v：参考图放 input.media
    input_obj = build_video_input(prompt, data_uri)

    parameters = {
        "resolution": "720P",
        "duration": max(2, min(int(duration), 10)),
        "prompt_extend": True,
        "watermark": False,
        "negative_prompt": "static image, no movement, frozen, still frame, slideshow, "
                           "low quality, blurry, distorted face, deformed hands, "
                           "multiple limbs, bad anatomy, watermark, text overlay",
    }
    # i2v 不支持 ratio 参数（宽高比随首帧图）；r2v 才传 ratio
    if not is_i2v_model():
        parameters["ratio"] = "16:9"

    payload = {
        "model": VIDEO_MODEL,
        "input": input_obj,
        "parameters": parameters,
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

    index_path = project_dir / video_index_filename(use_tts)
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

        output_path = clips_dir / clip_filename(i, use_tts)

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
