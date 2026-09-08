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
    """获取音视频文件时长（秒）；缺失/失败返回 0.0（统一委托 ffmpeg_utils）"""
    from ..utils.ffmpeg_utils import probe_duration
    return probe_duration(media_path)


def _has_audio_stream(media_path: str) -> bool:
    """探测媒体文件是否带音轨（统一委托 ffmpeg_utils）"""
    from ..utils.ffmpeg_utils import probe_has_audio
    return probe_has_audio(media_path)


def _build_subtitle_text(shot: Shot) -> str:
    """构建字幕文本（多条对白/旁白各自独立一行；再做自适应断行）"""
    parts = []
    if shot.dialogues:
        for d in shot.dialogues:
            if d.line:
                parts.append(f"{d.character}：{d.line}")
    if shot.narrator:
        parts.append(shot.narrator)
    return "\n".join(parts) if parts else ""


def _display_width(text: str) -> int:
    """估算显示宽度：中文/全角按 2 单位，其余按 1"""
    w = 0
    for ch in text:
        w += 2 if ord(ch) > 0x2E7F else 1  # CJK 及全角
    return w


def _wrap_line(text: str, max_width: int) -> list:
    """按显示宽度贪心断行（尽量在标点后断，避免把一个词切断）"""
    if _display_width(text) <= max_width:
        return [text]
    lines = []
    cur = ""
    cur_w = 0
    for ch in text:
        cw = _display_width(ch)
        if cur_w + cw > max_width:
            # 尝试回退到最近断点
            cut = -1
            for i in range(len(cur) - 1, -1, -1):
                if cur[i] in "，。！？；：、,.!?;: ":
                    cut = i + 1
                    break
            if cut > 0:
                lines.append(cur[:cut])
                cur = cur[cut:]
            else:
                lines.append(cur)
                cur = ""
            cur_w = _display_width(cur)
        cur += ch
        cur_w += cw
    if cur:
        lines.append(cur)
    return lines


def _format_subtitle_for_drawtext(shot: Shot) -> dict:
    """把镜头字幕格式化为可安全进 drawtext 的多行文本。

    目标（1920×1080）：整段字幕不超出画面——左右用断行限制宽度，
    上下用“总高 = 行数 × 字号 ≤ ~200px”限制，超长自动缩小字号且不丢字。
    返回 {"text": 真实换行分隔的多行文本, "lines": 行数, "fontsize": 字号}
    """
    raw = _build_subtitle_text(shot)
    if not raw:
        return {"text": "", "lines": 0, "fontsize": 36}

    # 第一遍：按可读宽度断行（每行上限 28 全角≈56 显示宽，留边距）
    def _reflow(width):
        out = []
        for seg in raw.split("\n"):
            out.extend(_wrap_line(seg, width))
        return out

    lines = _reflow(56)
    # 若行数过多，逐步放宽单行宽度以减少行数（不超画面宽 70 上限）
    for width in (60, 64, 68, 72):
        if len(lines) <= 5:
            break
        lines = _reflow(width)

    # 行数对应的字号：3行28、4行24、5行21、6行18……保证总高 ~200px 内
    fontsize = max(16, int(200 / max(len(lines), 1) / 1.35))
    return {"text": "\n".join(lines), "lines": len(lines), "fontsize": fontsize}


def _escape_drawtext(text: str) -> str:
    """转义 drawtext 文本中的特殊字符（含把换行转成 drawtext 能识别的 \\n）"""
    text = text.replace("\\", "\\\\")
    text = text.replace("\n", "\\n")
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
    use_tts: bool = True,
) -> str:
    """
    合成最终视频。
    use_tts=True : 丢弃 AI 视频原声，只保留 TTS 对白/旁白 + 字幕
    use_tts=False: 保留 AI 视频原画面与原声直接拼接，不叠加配音
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
        if not use_tts:
            # 原声模式：忽略配音，直接拼 AI 片段原声
            dialogue_audio = None
            narrator_audio = None
        else:
            dialogue_audio = audio_info.get("dialogue_audio")
            narrator_audio = audio_info.get("narrator_audio")

        # 确定时长
        if use_tts:
            # 对话+旁白顺序播放，总时长 = 两者之和，并覆盖镜头基础时长
            audio_duration = 0.0
            if dialogue_audio:
                audio_duration += _get_media_duration(dialogue_audio)
            if narrator_audio:
                audio_duration += _get_media_duration(narrator_audio)
            duration = max(shot.duration, audio_duration)
        else:
            # 原声模式：时长 = AI 视频自身长度（保留完整画面与声音），无视频则用镜头基础时长
            video_len = _get_media_duration(video_source) if video_source else 0.0
            duration = video_len if video_source else max(shot.duration, video_len)

        temp_output = output_dir / f"temp_clip_{i:04d}.mp4"

        # 构建滤镜
        filter_parts = []
        video_filters = []

        # 字幕滤镜（多行自动换行 + 行数多时缩小字号，避免超出画面）
        sub = _format_subtitle_for_drawtext(shot)
        if sub["text"]:
            escaped = _escape_drawtext(sub["text"])
            video_filters.append(
                f"drawtext=fontfile='{FONT_PATH}':text='{escaped}':"
                f"fontcolor=white:fontsize={sub['fontsize']}:borderw=2:bordercolor=black:"
                f"line_spacing=10:x=(w-text_w)/2:y=h-text_h-70"
            )

        cmd = [FFMPEG_PATH, "-y"]

        # 视频输入
        if video_source:
            video_duration = _get_media_duration(video_source)
            cmd.extend(["-i", video_source])
            video_label = "0:v"
            has_video_audio = _has_audio_stream(video_source)
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
        if use_tts and dialogue_audio:
            dialogue_idx = next_input_idx
            cmd.extend(["-i", dialogue_audio])
            next_input_idx += 1
        if use_tts and narrator_audio:
            narrator_idx = next_input_idx
            cmd.extend(["-i", narrator_audio])
            next_input_idx += 1

        # 构建音频逻辑
        voice_inputs = []
        if dialogue_idx is not None:
            voice_inputs.append(f"[{dialogue_idx}:a]")
        if narrator_idx is not None:
            voice_inputs.append(f"[{narrator_idx}:a]")

        if not use_tts:
            # 原声模式：直接取 AI 视频原音轨；无则静音
            if has_video_audio:
                audio_map = "0:a"
            else:
                cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
                audio_map = f"{next_input_idx}:a"
        elif voice_inputs:
            # 配音模式：TTS 人声(对话1.0 / 旁白0.85) + AI 视频原声(环境音) 垫底
            voice_labels = []
            if dialogue_idx is not None:
                filter_parts.append(
                    f"[{dialogue_idx}:a]volume=1.0,atrim=0:{duration},asetpts=PTS-STARTPTS,"
                    f"aformat=sample_rates=44100:channel_layouts=stereo[vd]"
                )
                voice_labels.append("[vd]")
            if narrator_idx is not None:
                filter_parts.append(
                    f"[{narrator_idx}:a]volume=0.7,atrim=0:{duration},asetpts=PTS-STARTPTS,"
                    f"aformat=sample_rates=44100:channel_layouts=stereo[vn]"
                )
                voice_labels.append("[vn]")
            if len(voice_labels) == 1:
                voice_filter = f"{voice_labels[0]}anull[voice]"
            else:
                joined = "".join(voice_labels)
                voice_filter = f"{joined}concat=n={len(voice_labels)}:v=0:a=1[voice]"
            filter_parts.append(voice_filter)
            # 配音镜头只放 TTS 人声，不掺 AI 原声（避免自带说话/环境与配音重叠）
            audio_map = "[voice]"
        elif has_video_audio:
            # 配音模式但该镜头无台词：保留视频原声（环境音）
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
