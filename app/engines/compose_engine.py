"""视频合成引擎 - 画面/视频片段 + 音频 + 字幕 → 最终视频"""
import subprocess
from pathlib import Path
from ..models import Shot

# 使用 imageio-ffmpeg 内置的 FFmpeg
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_PATH = "ffmpeg"  # 回退到系统 FFmpeg

# Windows 中文字体
FONT_PATH = "C\\:/Windows/Fonts/msyh.ttc"


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


def _build_subtitle_text(shot: Shot) -> str:
    """构建字幕文本"""
    parts = []
    if shot.dialogues:
        for d in shot.dialogues:
            if d.line:
                parts.append(f"{d.character}：{d.line}")
    if shot.narrator:
        parts.append(shot.narrator)
    return "\n".join(parts) if parts else ""


def _escape_drawtext(text: str) -> str:
    """转义 drawtext 文本中的特殊字符"""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


async def compose_final_video(
    shots: list[Shot],
    shot_image_paths: list[str],
    video_clip_paths: list[str],
    audio_paths: list[dict],
    project_dir: Path,
) -> str:
    """
    合成最终视频。
    优先使用 AI 视频片段，没有则用静态画面。
    """
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 第一步：为每个分镜生成带音频和字幕的片段
    temp_clips = []
    for i, shot in enumerate(shots):
        video_source = video_clip_paths[i] if i < len(video_clip_paths) and video_clip_paths[i] else None
        image_source = shot_image_paths[i] if i < len(shot_image_paths) else None

        if not video_source and not image_source:
            continue

        audio_info = audio_paths[i] if i < len(audio_paths) else {}
        dialogue_audio = audio_info.get("dialogue_audio")
        narrator_audio = audio_info.get("narrator_audio")

        # 确定时长（对话+旁白顺序播放，总时长 = 两者之和）
        audio_duration = 0.0
        if dialogue_audio:
            audio_duration += _get_media_duration(dialogue_audio)
        if narrator_audio:
            audio_duration += _get_media_duration(narrator_audio)
        duration = max(shot.duration, audio_duration)

        temp_output = output_dir / f"temp_clip_{i:04d}.mp4"
        subtitle_text = _build_subtitle_text(shot)

        # 构建滤镜
        filter_parts = []
        video_filters = []

        # 字幕滤镜
        if subtitle_text:
            escaped = _escape_drawtext(subtitle_text)
            video_filters.append(
                f"drawtext=fontfile='{FONT_PATH}':text='{escaped}':"
                f"fontcolor=white:fontsize=36:borderw=2:bordercolor=black:"
                f"x=(w-text_w)/2:y=h-text_h-60"
            )

        cmd = [FFMPEG_PATH, "-y"]

        # 视频输入
        if video_source:
            video_duration = _get_media_duration(video_source)
            cmd.extend(["-i", video_source])
            video_label = "0:v"
            has_video_audio = True
            # 视频不够长时，冻结最后一帧延长（不循环播放）
            if video_duration < duration:
                pad_time = duration - video_duration
                video_filters.insert(0, f"tpad=stop_mode=clone:stop_duration={pad_time}")
        else:
            cmd.extend(["-loop", "1", "-i", image_source])
            video_filters.insert(0, f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
            video_label = "0:v"
            has_video_audio = False

        # 音频输入（对话 + 旁白）
        next_input_idx = 1
        dialogue_idx = None
        narrator_idx = None
        if dialogue_audio:
            dialogue_idx = next_input_idx
            cmd.extend(["-i", dialogue_audio])
            next_input_idx += 1
        if narrator_audio:
            narrator_idx = next_input_idx
            cmd.extend(["-i", narrator_audio])
            next_input_idx += 1

        # 构建音频逻辑
        voice_inputs = []
        if dialogue_idx is not None:
            voice_inputs.append(f"[{dialogue_idx}:a]")
        if narrator_idx is not None:
            voice_inputs.append(f"[{narrator_idx}:a]")

        if voice_inputs:
            # 有配音：抹掉视频原声，只用配音
            if len(voice_inputs) == 1:
                # 单个音频直接用
                voice_filter = f"{voice_inputs[0]}atrim=0:{duration},asetpts=PTS-STARTPTS[outa]"
            else:
                # 多个音频：对话优先，旁白跟在后面（先后播放，不混音）
                # 先拼接：对话在前，旁白在后
                joined = "".join(voice_inputs)
                voice_filter = f"{joined}concat=n={len(voice_inputs)}:v=0:a=1[outa]"
            filter_parts.append(voice_filter)
            audio_map = "[outa]"
        elif has_video_audio:
            # 无配音：保留视频原声（环境音）
            audio_map = "0:a"
        else:
            # 无任何音频：静音
            cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
            audio_map = f"{next_input_idx}:a"

        # 视频滤镜
        if video_filters:
            video_filter = ",".join(video_filters)
            filter_parts.insert(0, f"[{video_label}]{video_filter}[v]")
            video_map = "[v]"
        else:
            video_map = video_label

        # 应用 filter_complex
        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", video_map, "-map", audio_map])
        else:
            cmd.extend(["-map", video_map, "-map", audio_map])

        # 输出参数
        cmd.extend([
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-pix_fmt", "yuv420p",
            str(temp_output),
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"分镜 {i} 合成失败: {result.stderr[-300:]}")
                continue
            temp_clips.append(temp_output)
        except Exception as e:
            print(f"分镜 {i} 合成异常: {e}")
            continue

    if not temp_clips:
        raise ValueError("没有成功合成的片段")

    # 第二步：拼接所有片段
    concat_list = output_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for clip in temp_clips:
            # 用文件名（因为 concat_list 和 temp_clips 在同一目录）
            f.write(f"file '{clip.name}'\n")

    final_output = output_dir / "final_video.mp4"
    concat_cmd = [
        FFMPEG_PATH, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(final_output),
    ]

    result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        # 如果 copy 模式失败，重新编码
        concat_cmd = [
            FFMPEG_PATH, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            str(final_output),
        ]
        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise ValueError(f"拼接失败: {result.stderr[-300:]}")

    # 清理临时文件
    for clip in temp_clips:
        clip.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    return str(final_output)
