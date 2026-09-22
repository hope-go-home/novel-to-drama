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
from ..utils.video_motion import motion_curve, find_peaks

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


def _resolve_sfx_asset(name: str):
    """匹配音效素材：先 sfx 分类；找不到再跨类回退 ambience / transition。
    这样"风声"这类只有环境音素材的名字也能被用作音效。
    """
    if not name:
        return None
    f = _asset_path("sfx", _match_keyword("sfx", name))
    if f:
        return f
    f = _asset_path("ambience", _match_keyword("ambience", name))
    if f:
        return f
    f = _asset_path("sfx", _match_keyword("transition", name))
    if f:
        return f
    return None


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


def _sfx_volume_scale(name: str) -> float:
    """按音效名（子串匹配）取额外音量倍率，默认 1.0（见 audio_map.json 的 sfx_vol）"""
    m = _load_map().get("sfx_vol") or {}
    if not m or not name:
        return 1.0
    nm = str(name).strip()
    if nm in m:
        try:
            return float(m[nm])
        except Exception:
            return 1.0
    for k, v in m.items():
        if not k or k.startswith("_"):
            continue
        if k in nm or nm in k:
            try:
                return float(v)
            except Exception:
                continue
    return 1.0


def _run(cmd: list) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False


def _seg_index(p: Path) -> int:
    """从 shot_XXXX_dialogue_{j}.mp3 取出 j（用于按句顺序排序）"""
    try:
        return int(p.stem.rsplit("_", 1)[-1])
    except Exception:
        return 0


def _dialogue_line_windows(project_dir: Path, shot_index: int, shot: Shot) -> list:
    """推导该镜头每句对白在"对白音频"内的时间窗 [(start, end, text)]。
    优先用逐句配音缓存 shot_XXXX_dialogue_{j}.mp3 的时长累加；无分句则退回整段一个窗口。
    纯读取已有音频，不调用任何 TTS。
    """
    audio_dir = project_dir / "audio"
    lines = shot.dialogues or []
    segs = sorted(audio_dir.glob(f"shot_{shot_index:04d}_dialogue_*.mp3"), key=_seg_index)
    windows = []
    if segs:
        t = 0.0
        for j, p in enumerate(segs):
            d = probe_duration(str(p))
            if d <= 0:
                continue
            txt = lines[j].line if j < len(lines) else ""
            windows.append((t, t + d, txt))
            t += d
        if windows:
            return windows

    merged = audio_dir / f"shot_{shot_index:04d}_dialogue.mp3"
    if merged.exists():
        d = probe_duration(str(merged))
        if d > 0:
            txt = lines[0].line if lines else ""
            return [(0.0, d, txt)]
    return []


def _match_line_for_event(name: str, line_windows: list) -> int:
    """找与该音效名最匹配的台词窗口下标；无匹配返回 -1"""
    if not name or not line_windows:
        return -1
    nm = str(name).strip()
    for k, (_s, _e, txt) in enumerate(line_windows):
        if not txt:
            continue
        if nm in txt or txt in nm:
            return k
        for L in (3, 2):
            if len(nm) >= L and any(nm[i:i + L] in txt for i in range(len(nm) - L + 1)):
                return k
    return -1


def align_event_starts(events: list, line_windows: list = None, peaks: list = None, window: float = 0.6):
    """计算每个音效的对齐后起点，返回 (starts, sources)。
    events: [{"name":..., "start":...}]（按原 start 升序）
    规则：优先吸附到"对应台词句"的起点；再在附近 window 内尝试吸附画面运动峰。
    sources: line / line+motion / motion / script
    """
    peak_ts = [t for t, _ in (peaks or [])]
    used = set()
    starts, sources = [], []
    for ev in events:
        name = ev.get("name") or ""
        target = float(ev.get("start") or 0.0)
        src = "script"

        k = _match_line_for_event(name, line_windows or [])
        if k >= 0:
            target = float(line_windows[k][0])
            src = "line"

        if peak_ts:
            best_idx, best_d = None, None
            for idx, t in enumerate(peak_ts):
                if idx in used:
                    continue
                d = abs(t - target)
                if d <= window and (best_d is None or d < best_d):
                    best_idx, best_d = idx, d
            if best_idx is not None:
                used.add(best_idx)
                target = peak_ts[best_idx]
                src = "line+motion" if src == "line" else "motion"

        starts.append(max(0.0, target))
        sources.append(src)
    return starts, sources


def build_shot_sfx_track(
    shot: Shot, out_path: Path, transition_file: str = None, duration: float = 0,
    align_peaks: list = None, align_window: float = 0.6, align_debug: dict = None,
    line_windows: list = None,
) -> str:
    """按 sound_effects 生成单个镜头的音效轨；无匹配返回 None。
    transition_file：若该镜头是场景起点，可在 0 秒加一个转场音效。
    line_windows：该镜每句对白的时间窗，用于把音效吸附到"对应台词句"的起点。
    align_peaks：画面运动峰值 [(t, energy)]，用于把音效吸附到画面动作时刻。
    音效 start/end 会被归一化（夹到 [0, duration]、越界丢弃、按 start 排序）。
    """
    # 1) 收集并匹配音效事件
    events = []
    for e in (shot.sound_effects or []):
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        f = _resolve_sfx_asset(name)
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
        events.append((f, start, end, _parse_vol(e.get("vol")) * _sfx_volume_scale(name), name))

    events.sort(key=lambda x: x[1])

    # 2) 对齐：优先吸附到"对应台词句"，再叠加画面运动峰校正
    if events and (align_peaks or line_windows):
        ev_dicts = [{"name": ev[4], "start": ev[1]} for ev in events]
        starts = [ev[1] for ev in events]
        new_starts, sources = align_event_starts(ev_dicts, line_windows, align_peaks, align_window)
        if align_debug is not None:
            align_debug["events"] = [
                {"name": events[k][4], "orig": round(starts[k], 2),
                 "aligned": round(new_starts[k], 2), "source": sources[k]}
                for k in range(len(events))
            ]
        events = [
            (events[k][0], new_starts[k], events[k][2], events[k][3], events[k][4])
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
    sfx_names = []   # 每镜命中的音效名（供前端展示）
    amb_names = []   # 每镜对应的环境音描述（命中才有）
    for i, (sc, sh) in enumerate(flat):
        dur = durations[i]
        key = sc.scene_number

        # 记录该镜命中的音效名 / 环境音描述（与生成结果一并登记，供前端展示）
        sfx_names.append([
            (e.get("name") or "").strip()
            for e in (sh.sound_effects or [])
            if isinstance(e, dict) and _resolve_sfx_asset((e.get("name") or "").strip())
        ])
        _amb_txt = sc.ambience or sc.location or ""
        amb_names.append(_amb_txt if _match_in_text("ambience", _amb_txt) else "")

        # 画面运动峰值（把音效吸附到画面动作时刻）
        peaks = []
        clip = video_paths[i] if video_paths and i < len(video_paths) else None
        if SFX_MOTION_ALIGN and clip and Path(clip).exists():
            try:
                peaks = find_peaks(motion_curve(clip))
            except Exception:
                peaks = []

        # 句边界（优先把音效吸附到"对应台词句"的起点，零成本：读已有逐句配音缓存）
        line_windows = _dialogue_line_windows(project_dir, i, sh) if sh.dialogues else []

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
                dbg = None
                if peaks or line_windows:
                    entry = align_report.setdefault(i, {})
                    if clip and peaks:
                        entry["clip"] = Path(clip).name
                    if peaks:
                        entry["peaks"] = [round(t, 2) for t, _ in peaks]
                    if line_windows:
                        entry["lines"] = [[round(s, 2), round(e, 2), t] for s, e, t in line_windows]
                    dbg = entry
                sfx_paths.append(build_shot_sfx_track(
                    sh, sfx_out, transition_file=trans, duration=dur,
                    align_peaks=peaks or None, align_window=SFX_ALIGN_WINDOW,
                    align_debug=dbg, line_windows=line_windows or None,
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
            # 先按各场景情绪匹配；匹配不到的场景沿用上一段 BGM（不静音），
            # 并用第一个匹配到的情绪回填开头，避免整片中途断乐
            matched = [
                _match_keyword("bgm", scene_obj[key].bgm or scene_obj[key].mood or "")
                for key in scene_order
            ]
            seed = next((f for f in matched if f), None)
            last = seed
            segs = []
            for idx, key in enumerate(scene_order):
                fname = matched[idx] or last or seed
                if matched[idx]:
                    last = matched[idx]
                segs.append((_asset_path("bgm", fname), scene_dur[key]))
            bgm_path = build_bgm_track(segs, bgm_out)

    registry = {
        "sfx": sfx_paths,
        "ambience": amb_paths,
        "bgm": bgm_path,
        "durations": durations,
        "sfx_names": sfx_names,
        "ambience_name": amb_names,
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
