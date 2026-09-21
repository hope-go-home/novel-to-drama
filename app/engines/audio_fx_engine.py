"""音频增强引擎 - 本地素材库：音效(SFX)/环境音(Ambience)/BGM + 转场音
不依赖外部 API，全部用本地 assets/ 素材 + ffmpeg 实现。

- 音效：按剧本 shot.sound_effects[{name,start,end,vol}] 匹配素材 -> 裁时长 + 对时间点 + 音量
- 环境音：按 scene.ambience 关键词匹配素材 -> 循环铺满
- BGM：按 scene.bgm 情绪匹配素材 -> 各场景拼接成整片 BGM
- 匹配不到 -> 跳过（不生成）
"""
import json
import subprocess
from pathlib import Path

from ..config import (
    ASSETS_DIR, SFX_ENABLED, AMBIENCE_ENABLED, BGM_ENABLED, BGM_CROSSFADE,
    SFX_MOTION_ALIGN, SFX_ALIGN_WINDOW,
)
from ..models import Shot, Scene
from ..utils.logger import add_log
from ..utils.ffmpeg_utils import FFMPEG_PATH, probe_duration
from ..utils.video_motion import motion_curve, find_peaks, align_starts

_MAP_CACHE = None


def _load_map() -> dict:
    global _MAP_CACHE
    if _MAP_CACHE is None:
        p = ASSETS_DIR / "audio_map.json"
        try:
            _MAP_CACHE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:
            _MAP_CACHE = {}
    return _MAP_CACHE


def _asset_path(category: str, filename: str):
    """category -> assets 子目录；返回存在的路径或 None"""
    if not filename:
        return None
    p = ASSETS_DIR / category / filename
    return p if p.exists() else None


def _key_str(key) -> str:
    """场景编号安全转字符串，用于文件名"""
    try:
        return f"{int(key):04d}"
    except Exception:
        return str(key).replace("/", "_").replace("\\", "_")


def _match_keyword(category: str, key: str):
    """在 category 段里匹配（精确 -> 双向子串），返回文件名或 None"""
    m = _load_map().get(category, {})
    if not m or not key:
        return None
    key = str(key).strip()
    if key in m:
        return m[key]
    for k, f in m.items():
        if k and (k in key or key in k):
            return f
    return None


def _match_in_text(category: str, text: str):
    """在长文本里找出现的关键词（用于 scene.ambience 一句话描述）"""
    m = _load_map().get(category, {})
    if not m or not text:
        return None
    text = str(text)
    # 先精确，再关键词出现在文本中
    if text.strip() in m:
        return m[text.strip()]
    for k, f in m.items():
        if k and k in text:
            return f
    return None


def _parse_vol(v) -> float:
    """'-6dB' -> 0.5; 0.3 -> 0.3; 空 -> 1.0"""
    if v is None or v == "":
        return 1.0
    s = str(v).strip().lower()
    try:
        if s.endswith("db"):
            return round(10 ** (float(s[:-2]) / 20.0), 4)
        return float(s)
    except Exception:
        return 1.0


def _run(cmd: list) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False


def build_shot_sfx_track(
    shot: Shot, out_path: Path, transition_file: str = None, duration: float = 0,
    align_peaks: list = None, align_window: float = 0.6, align_debug: dict = None,
) -> str:
    """按 sound_effects 生成单个镜头的音效轨；无匹配返回 None。
    transition_file：若该镜头是场景起点，可在 0 秒加一个转场音效。
    align_peaks：画面运动峰值 [(t, energy)]，提供时把音效 start 吸附到窗口内最近的峰。
    音效 start/end 会被归一化（夹到 [0, duration]、越界丢弃、按 start 排序），
    保证音效不会落到镜头外导致错位。
    """
    # 1) 收集并匹配音效事件
    events = []
    for e in (shot.sound_effects or []):
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        fname = _match_keyword("sfx", name)
        f = _asset_path("sfx", fname)
        if not f:
            continue
        try:
            start = float(e.get("start") or 0.0)
        except Exception:
            start = 0.0
        try:
            end = float(e.get("end") or 0.0)
        except Exception:
            end = 0.0
        events.append((f, start, end, _parse_vol(e.get("vol")), name))

    events.sort(key=lambda x: x[1])

    # 2) 画面运动峰值对齐：把音效 start 吸附到最近的显著运动峰
    if align_peaks and events:
        starts = [ev[1] for ev in events]
        snapped = align_starts(starts, align_peaks, align_window)
        if align_debug is not None:
            align_debug["events"] = [
                {"name": events[k][4], "orig": round(starts[k], 2), "aligned": round(snapped[k], 2)}
                for k in range(len(events))
            ]
        events = [
            (events[k][0], snapped[k], events[k][2], events[k][3], events[k][4])
            for k in range(len(events))
        ]
        events.sort(key=lambda x: x[1])

    # 3) 归一化：夹到镜头时长内、越界丢弃
    total = float(duration or 0)
    clips = []  # (file, start, dur, vol)
    if transition_file:
        tf = _asset_path("sfx", transition_file)
        if tf:
            clips.append((tf, 0.0, None, 0.9))

    for f, start, end, vol, _name in events:
        start = max(0.0, start)
        if total > 0 and start >= total - 0.05:
            continue  # 起点已超出镜头，丢弃
        dur = (end - start) if end > start else None
        if dur and total > 0:
            dur = min(dur, total - start)  # 不越过镜头末尾
            if dur < 0.05:
                dur = None
        clips.append((f, start, dur, vol))

    if not clips:
        return None

    inputs = []
    fc = []
    for i, (f, start, dur, vol) in enumerate(clips):
        inputs += ["-i", str(f)]
        chain = f"[{i}:a]volume={vol},"
        if dur:
            chain += f"atrim=0:{dur},"
        ms = int(start * 1000)
        chain += f"adelay={ms}|{ms},aformat=sample_rates=44100:channel_layouts=stereo[s{i}];"
        fc.append(chain)
    mix_in = "".join(f"[s{i}]" for i in range(len(clips)))
    fc.append(f"{mix_in}amix=inputs={len(clips)}:duration=longest:normalize=0[out]")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG_PATH, "-y"] + inputs + [
        "-filter_complex", "".join(fc), "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
    ]
    return str(out_path) if _run(cmd) else None


def build_scene_ambience_track(amb_file: Path, duration: float, out_path: Path) -> str:
    """把环境音循环铺满指定时长（用于整个场景做成一条连续环境音）"""
    if not amb_file or duration <= 0:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_PATH, "-y", "-stream_loop", "-1", "-i", str(amb_file),
        "-t", str(duration),
        "-af", "aformat=sample_rates=44100:channel_layouts=stereo",
        "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
    ]
    return str(out_path) if _run(cmd) else None


def slice_audio(src: Path, start: float, duration: float, out_path: Path) -> str:
    """从一条连续音频里截取 [start, start+duration]（同一源切片 → 相邻镜头无缝连续，无重起感）"""
    if not src or duration <= 0:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
        "-i", str(src),
        "-af", "aformat=sample_rates=44100:channel_layouts=stereo",
        "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
    ]
    return str(out_path) if _run(cmd) else None


def _make_segment(bgm_file: Path, duration: float, out_path: Path) -> str:
    """生成一段指定时长的 BGM（不足循环，长则裁剪）；无素材返回 None"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if bgm_file:
        cmd = [
            FFMPEG_PATH, "-y", "-stream_loop", "-1", "-i", str(bgm_file),
            "-t", str(duration),
            "-af", "aformat=sample_rates=44100:channel_layouts=stereo",
            "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
        ]
    else:
        cmd = [
            FFMPEG_PATH, "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo", "-t", str(duration),
            "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
        ]
    return str(out_path) if _run(cmd) else None


def build_bgm_track(scene_segments: list, out_path: Path, crossfade: float = None) -> str:
    """scene_segments: [(bgm_file_or_None, duration)] -> 拼成整片 BGM。
    场景之间用 acrossfade 交叉淡化（可从配置 BGM_CROSSFADE 调），含片头淡入/片尾淡出。
    """
    if not scene_segments:
        return None
    if crossfade is None:
        crossfade = BGM_CROSSFADE
    crossfade = max(0.0, float(crossfade))

    seg_dir = out_path.parent
    valid = [(f, float(d)) for (f, d) in scene_segments if d and float(d) > 0]
    if not valid:
        return None

    n = len(valid)
    seg_files = []
    for idx, (f, dur) in enumerate(valid):
        # 非最后一段多留 crossfade 秒，用于补偿 acrossfade 造成的时长损耗
        extra = crossfade if (idx < n - 1) else 0.0
        seg = seg_dir / f"_bgm_seg_{idx:04d}.mp3"
        r = _make_segment(f, dur + extra, seg)
        if r:
            seg_files.append(seg)
    if not seg_files:
        return None

    tmp_out = seg_dir / "_bgm_joined.mp3"
    if len(seg_files) == 1 or crossfade <= 0:
        inputs = []
        for s in seg_files:
            inputs += ["-i", str(s)]
        filter_complex = "".join(f"[{i}:a]" for i in range(len(seg_files)))
        filter_complex += f"concat=n={len(seg_files)}:v=0:a=1[out]"
        ok = _run(
            [FFMPEG_PATH, "-y"] + inputs +
            ["-filter_complex", filter_complex, "-map", "[out]",
             "-c:a", "libmp3lame", "-b:a", "160k", str(tmp_out)]
        )
    else:
        inputs = []
        for s in seg_files:
            inputs += ["-i", str(s)]
        fc = []
        for k in range(len(seg_files)):
            fc.append(f"[{k}:a]aformat=sample_rates=44100:channel_layouts=stereo[b{k}]")
        prev = "b0"
        for k in range(1, len(seg_files)):
            out = f"x{k}"
            fc.append(f"[{prev}][b{k}]acrossfade=d={crossfade}:c1=tri:c2=tri[{out}]")
            prev = out
        ok = _run(
            [FFMPEG_PATH, "-y"] + inputs +
            ["-filter_complex", ";".join(fc), "-map", f"[{prev}]",
             "-c:a", "libmp3lame", "-b:a", "160k", str(tmp_out)]
        )

    if not ok:
        for s in seg_files:
            s.unlink(missing_ok=True)
        return None

    # 片头淡入 + 片尾淡出
    total = probe_duration(str(tmp_out))
    fade = min(1.5, max(0.5, (total or 0) / 10))
    af = f"afade=t=in:st=0:d={fade},afade=t=out:st={max(0, total - fade)}:d={fade}"
    ok2 = _run([
        FFMPEG_PATH, "-y", "-i", str(tmp_out), "-af", af,
        "-c:a", "libmp3lame", "-b:a", "160k", str(out_path),
    ])
    for s in seg_files:
        s.unlink(missing_ok=True)
    tmp_out.unlink(missing_ok=True)
    return str(out_path) if ok2 else None


def _shot_duration(shot: Shot, audio_info: dict) -> float:
    """与合成一致的镜头时长：有配音取 max(镜头时长, 对白+旁白)，否则镜头时长"""
    d = probe_duration(audio_info.get("dialogue_audio")) if audio_info else 0
    n = probe_duration(audio_info.get("narrator_audio")) if audio_info else 0
    voice = d + n
    if voice > 0:
        return max(float(shot.duration or 3.0), voice)
    return float(shot.duration or 3.0)


def generate_audio_tracks(project, project_dir: Path, audio_paths: list = None, video_paths: list = None) -> dict:
    """生成整片音频增强轨（音效/环境音/BGM），登记 audio_tracks.json。
    audio_paths：各镜头配音信息，用于计算镜头时长。
    video_paths：各镜头视频片段（预留：用于按画面运动对齐音效）。
    """
    add_log("INFO", "audiofx", "开始生成音效/环境音/BGM", getattr(project, "id", ""))
    flat = []  # (scene, shot)
    if project.script:
        for sc in project.script.scenes:
            for sh in sc.shots:
                flat.append((sc, sh))

    sfx_dir = project_dir / "sfx"
    amb_dir = project_dir / "ambience"
    bgm_dir = project_dir / "bgm"

    sfx_paths = []
    amb_paths = []
    scene_order = []
    scene_dur = {}
    scene_obj = {}
    scene_offset = []  # 每个镜头在其所属场景内的起始偏移（用于环境音切片）

    durations = []
    seen = {}
    for i, (sc, sh) in enumerate(flat):
        info = (audio_paths[i] if audio_paths and i < len(audio_paths) else {}) or {}
        d = _shot_duration(sh, info)
        durations.append(d)
        key = sc.scene_number
        scene_offset.append(seen.get(key, 0.0))
        seen[key] = seen.get(key, 0.0) + d
        if key not in scene_dur:
            scene_dur[key] = 0.0
            scene_order.append(key)
            scene_obj[key] = sc
        scene_dur[key] += d

    # 每个场景构建一条连续环境音（整段），随后按镜头切片 → 相邻镜头无缝、无重起感
    scene_amb = {}
    if AMBIENCE_ENABLED:
        for key in scene_order:
            sc = scene_obj[key]
            af_name = _match_in_text("ambience", sc.ambience or sc.location or "")
            af = _asset_path("ambience", af_name)
            if not af or scene_dur[key] <= 0:
                scene_amb[key] = None
                continue
            st_path = amb_dir / f"scene_{_key_str(key)}.mp3"
            if not st_path.exists():
                build_scene_ambience_track(af, scene_dur[key], st_path)
            scene_amb[key] = str(st_path) if st_path.exists() else None

    align_report = {}
    for i, (sc, sh) in enumerate(flat):
        dur = durations[i]
        key = sc.scene_number

        # 画面运动峰值（用于把音效吸附到画面动作时刻）
        peaks = []
        clip = video_paths[i] if video_paths and i < len(video_paths) else None
        if SFX_MOTION_ALIGN and clip and Path(clip).exists():
            try:
                peaks = find_peaks(motion_curve(clip))
            except Exception:
                peaks = []

        # 音效轨（场景首个镜头带转场音效，按场景情绪选型）
        sfx_out = sfx_dir / f"shot_{i:04d}.mp3"
        if SFX_ENABLED:
            if sfx_out.exists():
                sfx_paths.append(str(sfx_out))
            else:
                is_scene_start = (i > 0 and flat[i - 1][0].scene_number != key)
                trans = None
                if is_scene_start:
                    tk = _match_keyword("transition_mood", sc.mood or "")
                    trans = _match_keyword("transition", tk) if tk else None
                    if not trans:
                        trans = _match_keyword("transition", "impact")
                if peaks:
                    align_report.setdefault(i, {})["clip"] = Path(clip).name
                    align_report[i]["peaks"] = [round(t, 2) for t, _ in peaks]
                    dbg = align_report[i]
                else:
                    dbg = None
                sfx_paths.append(build_shot_sfx_track(
                    sh, sfx_out, transition_file=trans, duration=dur,
                    align_peaks=peaks or None, align_window=SFX_ALIGN_WINDOW, align_debug=dbg,
                ))
        else:
            sfx_paths.append(None)

        # 环境音轨（从本场景连续轨按镜头偏移切片）
        amb_out = amb_dir / f"shot_{i:04d}.mp3"
        if AMBIENCE_ENABLED:
            if amb_out.exists():
                amb_paths.append(str(amb_out))
            else:
                src = scene_amb.get(key)
                p = slice_audio(Path(src), scene_offset[i], dur, amb_out) if src else None
                amb_paths.append(p)
        else:
            amb_paths.append(None)

    # BGM：按场景情绪拼接成整片
    bgm_path = None
    if BGM_ENABLED:
        bgm_out = bgm_dir / "bgm.mp3"
        if bgm_out.exists():
            bgm_path = str(bgm_out)
        else:
            segs = []
            for key in scene_order:
                sc = scene_obj[key]
                fname = _match_keyword("bgm", sc.bgm or sc.mood or "")
                segs.append((_asset_path("bgm", fname), scene_dur[key]))
            bgm_path = build_bgm_track(segs, bgm_out)

    registry = {
        "sfx": sfx_paths,
        "ambience": amb_paths,
        "bgm": bgm_path,
        "durations": durations,
    }
    (project_dir / "audio_tracks.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    if align_report:
        (project_dir / "align.json").write_text(
            json.dumps(align_report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    ok_sfx = sum(1 for p in sfx_paths if p)
    ok_amb = sum(1 for p in amb_paths if p)
    add_log("SUCCESS", "audiofx",
            f"音频轨完成：音效 {ok_sfx}/{len(flat)}、环境音 {ok_amb}/{len(flat)}、BGM {'有' if bgm_path else '无'}",
            getattr(project, "id", ""))
    return registry
