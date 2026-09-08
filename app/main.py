"""FastAPI 主入口 - 小说转漫剧 API"""
import uuid
import json
import shutil
import traceback
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse

import asyncio
from .config import OUTPUT_DIR, ensure_project_dir, DAILY_BUDGET
from .models import Project, ProjectCreate, ProjectStatus, Script, ShotQuality
from .utils.logger import add_log, get_logs, clear_logs, logger
from .utils.event_bus import wait_log_update
from .utils.task_registry import set_task, get_task, clear_task

# 存储正在运行的任务，用于立即取消
_running_tasks: dict[str, asyncio.Task] = {}

app = FastAPI(title="小说转漫剧 API", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理 - 记录所有未捕获的异常"""
    error_detail = traceback.format_exc()
    logger.error(f"未捕获异常: {request.method} {request.url.path} | {str(exc)}\n{error_detail}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {str(exc)}"},
    )

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(OUTPUT_DIR.parent)), name="static")


# ============ 工具函数 ============

def _save_project(project: Project):
    project_dir = ensure_project_dir(project.id)
    (project_dir / "project.json").write_text(
        json.dumps(project.model_dump(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _load_project(project_id: str) -> Project:
    json_path = OUTPUT_DIR / project_id / "project.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    return Project(**json.loads(json_path.read_text(encoding="utf-8")))


def _load_json(project_id: str, filename: str):
    path = OUTPUT_DIR / project_id / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_json(project_id: str, filename: str, data):
    path = OUTPUT_DIR / project_id / filename
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def _get_all_shots(project: Project):
    shots = []
    if project.script:
        for scene in project.script.scenes:
            shots.extend(scene.shots)
    return shots


def _is_cancelled(project_id: str) -> bool:
    """检查项目是否被取消（保留兼容性）"""
    return project_id not in _running_tasks


# ============ 任务 / 成本 / 质量 辅助 ============

async def _launch_task(project_id: str, step: str, coro):
    """启动后台任务并写入任务注册表（Redis 持久化，便于重启可查/多 worker 演进）"""
    task = asyncio.create_task(coro)
    _running_tasks[project_id] = task
    await set_task(project_id, step, "running")

    async def _finalize():
        cancelled = task.cancelled()
        try:
            p = _load_project(project_id) if not cancelled else None
            status = "cancelled" if cancelled else (p.status.value if p else "done")
        except Exception:
            status = "done" if not cancelled else "cancelled"
        await set_task(project_id, step, status, message=p.error_message[:200] if not cancelled and p else "")

    def _on_done(t):
        try:
            asyncio.ensure_future(_finalize())
        except Exception:
            pass
        _running_tasks.pop(project_id, None)

    task.add_done_callback(_on_done)
    return task


async def _record_usage(project_id: str, step: str, unit: float):
    """记录本次步骤成本（Redis 原子记账，不可用时内存兜底）"""
    try:
        from .engines.cost_engine import record_cost
        spent = await record_cost(project_id, step, unit)
        add_log("INFO", "cost", f"「{step}」已记账，累计 ¥{spent:.2f}", project_id)
    except Exception as e:
        logger.warning(f"成本记账失败: {e}")


async def _budget_guard(project_id: str, step: str, unit: float) -> bool:
    """生成前预算检查：返回 True=允许；False=超预算，自动把步骤置为错误并提示降级"""
    try:
        from .engines.cost_engine import check_budget
        ok, hint = await check_budget(project_id, step, unit)
        if not ok:
            add_log("ERROR", "cost", hint, project_id)
            try:
                project = _load_project(project_id)
                project.status = ProjectStatus.ERROR
                project.error_message = hint
                _save_project(project)
            except Exception:
                pass
            return False
        return True
    except Exception as e:
        logger.warning(f"预算检查失败（放行）: {e}")
        return True


async def _assess_and_save_quality(project_id: str, shots, image_paths) -> list:
    """对已生成的分镜画面做质量评估并写入 shot_quality.json"""
    from .engines.quality_engine import assess_shot_images
    try:
        qualities = await assess_shot_images(shots, image_paths)
        data = [q.model_dump() if q else None for q in qualities]
        _save_json(project_id, "shot_quality.json", data)
        low = [i for i, q in enumerate(qualities) if q and not q.passed]
        if low:
            add_log("WARN", "quality", f"质量检查完成，{len(low)} 个画面未通过闸门: {low}", project_id)
        else:
            add_log("SUCCESS", "quality", f"质量检查通过: {sum(1 for q in qualities if q)} 个画面", project_id)
        return qualities
    except Exception as e:
        logger.warning(f"质量评估失败（跳过）: {e}")
        return []


# ============ 项目管理 ============

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    project_id = str(uuid.uuid4())[:8]
    project = Project(id=project_id, name=req.name, novel_text=req.novel_text, use_tts=req.use_tts)
    ensure_project_dir(project_id)
    _save_project(project)
    return {"project_id": project_id, "message": "项目创建成功"}


@app.post("/api/projects/{project_id}/stop")
async def stop_project(project_id: str):
    """立即停止正在运行的生成任务"""
    task = _running_tasks.get(project_id)
    if task and not task.done():
        task.cancel()
        add_log("WARN", "system", "收到停止请求，立即停止", project_id)
    else:
        add_log("WARN", "system", "没有正在运行的任务", project_id)
    await clear_task(project_id)

    # 更新项目状态
    try:
        project = _load_project(project_id)
        if project.status not in [ProjectStatus.DONE, ProjectStatus.CREATED]:
            project.status = ProjectStatus.ERROR
            project.error_message = "用户手动停止"
            _save_project(project)
    except Exception:
        pass

    return {"message": "已停止"}


@app.post("/api/projects/{target_id}/import-characters/{source_id}")
async def import_characters(target_id: str, source_id: str):
    """从另一个项目导入角色三视图"""
    source = _load_project(source_id)
    target = _load_project(target_id)

    if not source.characters:
        raise HTTPException(status_code=400, detail="源项目没有角色数据")

    # 复制角色图片文件
    source_dir = OUTPUT_DIR / source_id / "characters"
    target_dir = OUTPUT_DIR / target_id / "characters"
    target_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    for char_dir in source_dir.iterdir():
        if char_dir.is_dir():
            dest = target_dir / char_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(char_dir, dest)

    # 复制角色数据
    target.characters = source.characters
    _save_project(target)

    add_log("SUCCESS", "character", f"从项目 {source_id} 导入 {len(source.characters)} 个角色", target_id)
    return {"message": f"已导入 {len(source.characters)} 个角色", "characters": [c.character_name for c in source.characters]}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    project = _load_project(project_id)
    d = project.model_dump()
    
    # 检查图片文件是否存在
    shot_images = _load_json(project_id, "shot_images.json") or []
    d["shot_images"] = [p if p and Path(p).exists() else None for p in shot_images]
    
    # 检查音频文件是否存在
    audio_paths = _load_json(project_id, "audio_paths.json") or []
    validated_audio = []
    for a in audio_paths:
        if isinstance(a, dict):
            validated_audio.append({
                "dialogue_audio": a.get("dialogue_audio") if a.get("dialogue_audio") and Path(a["dialogue_audio"]).exists() else None,
                "narrator_audio": a.get("narrator_audio") if a.get("narrator_audio") and Path(a["narrator_audio"]).exists() else None,
            })
        else:
            validated_audio.append(a)
    d["audio_paths"] = validated_audio
    
    # 检查视频文件是否存在
    video_paths = _load_json(project_id, "video_paths.json") or []
    d["video_paths"] = [p if p and Path(p).exists() else None for p in video_paths]

    # 质量评估结果（分镜画面质量徽标）
    d["shot_qualities"] = _load_json(project_id, "shot_quality.json") or []

    # 成本统计（当日已花费）
    try:
        from .engines.cost_engine import get_project_spend
        d["spend"] = round(await get_project_spend(project_id), 2)
        d["daily_budget"] = DAILY_BUDGET
    except Exception:
        d["spend"] = 0.0
        d["daily_budget"] = DAILY_BUDGET

    return d


@app.post("/api/projects/{project_id}/settings")
async def update_project_settings(project_id: str, body: dict):
    """更新项目设置（当前仅 use_tts）"""
    project = _load_project(project_id)
    if "use_tts" in body:
        project.use_tts = bool(body["use_tts"])
    _save_project(project)
    return {"use_tts": project.use_tts, "message": "设置已更新"}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    project_dir = OUTPUT_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    shutil.rmtree(project_dir)
    return {"message": "项目已删除"}


@app.delete("/api/projects/{project_id}/script")
async def delete_script(project_id: str):
    """删除剧本"""
    project = _load_project(project_id)
    project.script = None
    project.status = ProjectStatus.CREATED
    _save_project(project)
    # 删除相关文件
    for f in ["shot_images.json", "audio_paths.json", "video_paths.json"]:
        p = OUTPUT_DIR / project_id / f
        if p.exists():
            p.unlink()
    return {"message": "剧本已删除"}


@app.delete("/api/projects/{project_id}/characters")
async def delete_characters(project_id: str):
    """删除角色设计"""
    project = _load_project(project_id)
    project.characters = []
    _save_project(project)
    char_dir = OUTPUT_DIR / project_id / "characters"
    if char_dir.exists():
        shutil.rmtree(char_dir)
    return {"message": "角色设计已删除"}


@app.delete("/api/projects/{project_id}/shots")
async def delete_shots(project_id: str):
    """删除分镜画面"""
    _load_project(project_id)
    shots_dir = OUTPUT_DIR / project_id / "shots"
    if shots_dir.exists():
        shutil.rmtree(shots_dir)
        shots_dir.mkdir()
    p = OUTPUT_DIR / project_id / "shot_images.json"
    if p.exists():
        p.unlink()
    return {"message": "分镜画面已删除"}


@app.delete("/api/projects/{project_id}/audio")
async def delete_audio(project_id: str):
    """删除语音"""
    _load_project(project_id)
    audio_dir = OUTPUT_DIR / project_id / "audio"
    if audio_dir.exists():
        shutil.rmtree(audio_dir)
        audio_dir.mkdir()
    p = OUTPUT_DIR / project_id / "audio_paths.json"
    if p.exists():
        p.unlink()
    return {"message": "语音已删除"}


@app.delete("/api/projects/{project_id}/videos")
async def delete_videos(project_id: str):
    """删除视频片段"""
    _load_project(project_id)
    clips_dir = OUTPUT_DIR / project_id / "video_clips"
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
        clips_dir.mkdir()
    p = OUTPUT_DIR / project_id / "video_paths.json"
    if p.exists():
        p.unlink()
    return {"message": "视频片段已删除"}


@app.delete("/api/projects/{project_id}/output")
async def delete_output(project_id: str):
    """删除最终合成视频"""
    _load_project(project_id)
    output_dir = OUTPUT_DIR / project_id / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
        output_dir.mkdir()
    return {"message": "最终视频已删除"}


@app.delete("/api/projects/{project_id}/shot/{index}")
async def delete_single_shot(project_id: str, index: int):
    """删除单张分镜画面"""
    _load_project(project_id)
    shot_path = OUTPUT_DIR / project_id / "shots" / f"shot_{index:04d}.png"
    if shot_path.exists():
        shot_path.unlink()
    # 更新 shot_images.json
    images = _load_json(project_id, "shot_images.json") or []
    if index < len(images):
        images[index] = None
        _save_json(project_id, "shot_images.json", images)
    return {"message": f"分镜 {index} 已删除"}


@app.delete("/api/projects/{project_id}/video/{index}")
async def delete_single_video(project_id: str, index: int):
    """删除单个视频片段"""
    _load_project(project_id)
    clip_path = OUTPUT_DIR / project_id / "video_clips" / f"clip_{index:04d}.mp4"
    if clip_path.exists():
        clip_path.unlink()
    # 更新 video_paths.json
    videos = _load_json(project_id, "video_paths.json") or []
    if index < len(videos):
        videos[index] = None
        _save_json(project_id, "video_paths.json", videos)
    return {"message": f"视频片段 {index} 已删除"}


@app.get("/api/projects")
async def list_projects():
    projects = []
    if OUTPUT_DIR.exists():
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir() and (d / "project.json").exists():
                try:
                    p = _load_project(d.name)
                    projects.append({"id": p.id, "name": p.name, "status": p.status})
                except Exception:
                    pass
    return projects


# ============ 单步生成（每步独立，复用已有产出） ============

async def _run_script_generation(project_id: str):
    from .engines.script_engine import generate_script
    project = _load_project(project_id)
    project.status = ProjectStatus.SCRIPT_GENERATING
    project.error_message = ""
    _save_project(project)
    add_log("INFO", "script", "开始生成剧本", project_id)
    try:
        project.script = await generate_script(project.novel_text)
        project.status = ProjectStatus.SCRIPT_DONE
        _save_project(project)
        add_log("SUCCESS", "script", f"剧本生成完成: {project.script.title}", project_id)
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "script", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"剧本生成失败: {str(e)}"
        _save_project(project)
        add_log("ERROR", "script", f"剧本生成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/generate-script")
async def generate_script_api(project_id: str):
    _load_project(project_id)
    if not await _budget_guard(project_id, "script", 2.0):
        return {"message": "预算不足，已阻止"}
    await _launch_task(project_id, "script", _run_script_generation(project_id))
    return {"message": "剧本生成已启动"}


async def _run_character_generation(project_id: str):
    from .engines.character_engine import generate_all_characters
    project = _load_project(project_id)
    if not project.script:
        project.status = ProjectStatus.ERROR
        project.error_message = "请先生成剧本"
        _save_project(project)
        return
    project.status = ProjectStatus.CHARACTERS_GENERATING
    project.error_message = ""
    _save_project(project)
    add_log("INFO", "character", "开始生成角色三视图", project_id)
    try:
        project.characters = await generate_all_characters(project.script.characters, OUTPUT_DIR / project_id)
        project.status = ProjectStatus.CHARACTERS_DONE
        _save_project(project)
        add_log("SUCCESS", "character", f"角色生成完成: {len(project.characters)} 个角色", project_id)
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "character", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"角色生成失败: {str(e)}"
        _save_project(project)
        add_log("ERROR", "character", f"角色生成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/generate-characters")
async def generate_characters_api(project_id: str):
    project = _load_project(project_id)
    n = len(project.script.characters) if project.script else 0
    if not await _budget_guard(project_id, "characters", float(max(n, 1))):
        return {"message": "预算不足，已阻止"}
    await _launch_task(project_id, "characters", _run_character_generation(project_id))
    return {"message": "角色生成已启动"}


async def _run_shot_generation(project_id: str):
    from .engines.shot_engine import generate_shot_image_single
    project = _load_project(project_id)
    if not project.script:
        project.status = ProjectStatus.ERROR
        project.error_message = "请先生成剧本"
        _save_project(project)
        return
    project.status = ProjectStatus.SHOTS_GENERATING
    project.error_message = ""
    _save_project(project)
    all_shots = _get_all_shots(project)
    add_log("INFO", "shot", f"开始生成分镜画面: {len(all_shots)} 个镜头", project_id)

    # 预算检查（生图估算：按全部镜头张数；已有画面会跳过，此处为上限估算）
    if not await _budget_guard(project_id, "shots", float(len(all_shots))):
        return

    # 加载已有进度
    existing = _load_json(project_id, "shot_images.json") or []
    image_paths = existing + [None] * (len(all_shots) - len(existing))

    try:
        for i, shot in enumerate(all_shots):
            # 跳过已生成的
            if image_paths[i] is not None:
                add_log("INFO", "shot", f"镜头 {i} 已有画面，跳过", project_id)
                continue
            try:
                output_path = OUTPUT_DIR / project_id / "shots" / f"shot_{i:04d}.png"
                result = await generate_shot_image_single(shot, output_path, project.characters)
                image_paths[i] = result
                _save_json(project_id, "shot_images.json", image_paths)  # 每生成一个就保存
                add_log("SUCCESS", "shot", f"镜头 {i} 画面完成", project_id)
            except asyncio.CancelledError:
                _save_json(project_id, "shot_images.json", image_paths)
                raise
            except Exception as e:
                add_log("WARN", "shot", f"镜头 {i} 画面失败: {str(e)[:50]}", project_id)
                image_paths[i] = None

        project.status = ProjectStatus.SHOTS_DONE
        _save_project(project)
        _save_json(project_id, "shot_images.json", image_paths)
        ok_count = sum(1 for p in image_paths if p is not None)
        add_log("SUCCESS", "shot", f"分镜画面完成: {ok_count}/{len(all_shots)} 成功", project_id)
        # 质量闸门：评估本次新增画面，标记低质镜头（低质不进视频环节）
        await _assess_and_save_quality(project_id, all_shots, image_paths)
        # 成本记账：生图按成功张数
        await _record_usage(project_id, "shots", float(ok_count))
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "shot", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"画面生成失败: {str(e)}"
        _save_project(project)
        _save_json(project_id, "shot_images.json", image_paths)
        add_log("ERROR", "shot", f"画面生成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/generate-shots")
async def generate_shots_api(project_id: str):
    _load_project(project_id)
    await _launch_task(project_id, "shots", _run_shot_generation(project_id))
    return {"message": "分镜画面生成已启动"}


async def _run_audio_generation(project_id: str):
    from .engines.audio_engine import generate_shot_audio
    project = _load_project(project_id)
    if not project.script:
        project.status = ProjectStatus.ERROR
        project.error_message = "请先生成剧本"
        _save_project(project)
        return
    project.status = ProjectStatus.AUDIO_GENERATING
    project.error_message = ""
    _save_project(project)
    all_shots = _get_all_shots(project)
    add_log("INFO", "audio", f"开始生成语音: {len(all_shots)} 个镜头", project_id)

    # 加载已有进度
    existing = _load_json(project_id, "audio_paths.json") or []
    audio_paths = existing + [{"dialogue_audio": None, "narrator_audio": None}] * (len(all_shots) - len(existing))

    try:
        for i, shot in enumerate(all_shots):
            # 检查音频是否真正存在（不仅看JSON，还要检查文件）
            dialogue_ok = audio_paths[i].get("dialogue_audio") and Path(audio_paths[i]["dialogue_audio"]).exists()
            narrator_ok = audio_paths[i].get("narrator_audio") and Path(audio_paths[i]["narrator_audio"]).exists()
            
            # 如果JSON中有路径但文件不存在，清除路径
            if audio_paths[i].get("dialogue_audio") and not dialogue_ok:
                audio_paths[i]["dialogue_audio"] = None
            if audio_paths[i].get("narrator_audio") and not narrator_ok:
                audio_paths[i]["narrator_audio"] = None
            
            # 判断是否需要生成
            has_dialogue = shot.dialogues and any(d.line.strip() for d in shot.dialogues)
            needs_dialogue = has_dialogue and not dialogue_ok
            needs_narrator = shot.narrator and shot.narrator.strip() and not narrator_ok
            
            if not needs_dialogue and not needs_narrator:
                add_log("INFO", "audio", f"镜头 {i} 已有音频，跳过", project_id)
                continue
            try:
                result = await generate_shot_audio(shot, i, OUTPUT_DIR / project_id, project.script.characters)
                audio_paths[i] = result
                _save_json(project_id, "audio_paths.json", audio_paths)  # 每生成一个就保存
                add_log("SUCCESS", "audio", f"镜头 {i} 语音完成", project_id)
            except asyncio.CancelledError:
                _save_json(project_id, "audio_paths.json", audio_paths)
                raise
            except Exception as e:
                add_log("WARN", "audio", f"镜头 {i} 语音失败: {str(e)[:50]}", project_id)
                audio_paths[i] = {"dialogue_audio": None, "narrator_audio": None}

        project.status = ProjectStatus.AUDIO_DONE
        _save_project(project)
        _save_json(project_id, "audio_paths.json", audio_paths)
        ok_count = sum(1 for a in audio_paths if a.get("dialogue_audio") or a.get("narrator_audio"))
        add_log("SUCCESS", "audio", f"语音生成完成: {ok_count}/{len(all_shots)} 成功", project_id)
        # 成本记账：TTS 按预估字符量（每段对白+旁白字数），单位=千字符
        total_chars = sum(
            sum(len(d.line) for d in s.dialogues if d.line) + len(s.narrator or "")
            for s in all_shots
        ) / 1000.0
        await _record_usage(project_id, "audio", round(total_chars, 3))
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "audio", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"语音生成失败: {str(e)}"
        _save_project(project)
        _save_json(project_id, "audio_paths.json", audio_paths)  # 保存已有的进度
        add_log("ERROR", "audio", f"语音生成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/generate-audio")
async def generate_audio_api(project_id: str):
    project = _load_project(project_id)
    if project.use_tts is False:
        add_log("WARN", "audio", "当前为 AI 原声模式，跳过语音生成", project_id)
        return {"message": "AI 原声模式无需配音"}
    await _launch_task(project_id, "audio", _run_audio_generation(project_id))
    return {"message": "语音生成已启动"}


async def _run_video_generation(project_id: str):
    from .engines.video_engine import generate_video_clips
    project = _load_project(project_id)
    if not project.script:
        project.status = ProjectStatus.ERROR
        project.error_message = "请先生成剧本"
        _save_project(project)
        return
    project.status = ProjectStatus.VIDEO_GENERATING
    project.error_message = ""
    _save_project(project)
    all_shots = _get_all_shots(project)
    add_log("INFO", "video", f"开始生成 AI 视频: {len(all_shots)} 个镜头", project_id)

    # 预算检查：视频最贵，按镜头数×5秒估算
    if not await _budget_guard(project_id, "video", float(len(all_shots) * 5)):
        return

    try:
        image_paths = _load_json(project_id, "shot_images.json") or []
        audio_paths = _load_json(project_id, "audio_paths.json") or []
        video_paths = await generate_video_clips(all_shots, image_paths, OUTPUT_DIR / project_id, project_id, audio_paths)
        project.status = ProjectStatus.VIDEO_DONE
        _save_project(project)
        _save_json(project_id, "video_paths.json", video_paths)
        ok_count = sum(1 for p in video_paths if p)
        add_log("SUCCESS", "video", f"视频生成完成: {ok_count}/{len(all_shots)} 成功", project_id)
        # 成本记账：按成功视频 × 5 秒估算
        await _record_usage(project_id, "video", float(ok_count * 5))
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "video", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"视频生成失败: {str(e)}"
        _save_project(project)
        add_log("ERROR", "video", f"视频生成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/generate-videos")
async def generate_videos_api(project_id: str):
    _load_project(project_id)
    await _launch_task(project_id, "video", _run_video_generation(project_id))
    return {"message": "AI 视频生成已启动"}


async def _run_compose(project_id: str):
    from .engines.compose_engine import compose_final_video
    project = _load_project(project_id)
    if not project.script:
        project.status = ProjectStatus.ERROR
        project.error_message = "请先生成剧本"
        _save_project(project)
        return
    project.status = ProjectStatus.COMPOSING
    project.error_message = ""
    _save_project(project)
    add_log("INFO", "compose", "开始合成最终视频", project_id)
    try:
        all_shots = _get_all_shots(project)
        image_paths = _load_json(project_id, "shot_images.json") or []
        video_paths = _load_json(project_id, "video_paths.json") or []
        audio_paths = _load_json(project_id, "audio_paths.json") or []
        final_video = await compose_final_video(
            shots=all_shots, shot_image_paths=image_paths,
            video_clip_paths=video_paths, audio_paths=audio_paths,
            project_dir=OUTPUT_DIR / project_id, use_tts=project.use_tts,
        )
        project.status = ProjectStatus.DONE
        _save_project(project)
        (OUTPUT_DIR / project_id / "output" / "result.txt").write_text(final_video, encoding="utf-8")
        add_log("SUCCESS", "compose", f"视频合成完成: {final_video}", project_id)
    except asyncio.CancelledError:
        project.status = ProjectStatus.ERROR
        project.error_message = "用户手动停止"
        _save_project(project)
        add_log("WARN", "compose", "生成已停止", project_id)
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"合成失败: {str(e)}"
        _save_project(project)
        add_log("ERROR", "compose", f"合成失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/compose")
async def compose_api(project_id: str):
    _load_project(project_id)
    await _launch_task(project_id, "compose", _run_compose(project_id))
    return {"message": "视频合成已启动"}


# ============ 一键全流程 ============

async def _run_full_pipeline(project_id: str):
    """执行全流程，每步检查是否已有产出，跳过已完成的步骤"""
    from .engines.script_engine import generate_script
    from .engines.character_engine import generate_all_characters
    from .engines.shot_engine import generate_shot_images
    from .engines.audio_engine import generate_all_audio
    from .engines.compose_engine import compose_final_video

    project = _load_project(project_id)
    project_dir = OUTPUT_DIR / project_id

    try:
        # Step 1: 剧本（已有则跳过）
        if not project.script:
            if _is_cancelled(project_id): return
            project.status = ProjectStatus.SCRIPT_GENERATING
            _save_project(project)
            project.script = await generate_script(project.novel_text)
            project.status = ProjectStatus.SCRIPT_DONE
            _save_project(project)

        # Step 2: 角色三视图（引擎按三视图文件缓存，缺则补生成）
        if project.script:
            if _is_cancelled(project_id): return
            project.status = ProjectStatus.CHARACTERS_GENERATING
            _save_project(project)
            project.characters = await generate_all_characters(project.script.characters, project_dir)
            project.status = ProjectStatus.CHARACTERS_DONE
            _save_project(project)

        # Step 3: 分镜画面（已有则跳过）
        existing_images = _load_json(project_id, "shot_images.json")
        # 验证图片文件是否实际存在
        if existing_images:
            valid_images = []
            for p in existing_images:
                if p and Path(p).exists():
                    valid_images.append(p)
                else:
                    valid_images.append(None)
            # 如果所有图片都存在，才跳过
            if all(p is not None for p in valid_images):
                image_paths = valid_images
            else:
                existing_images = None  # 有缺失，需要重新生成
        
        if not existing_images:
            if _is_cancelled(project_id): return
            project.status = ProjectStatus.SHOTS_GENERATING
            _save_project(project)
            all_shots = _get_all_shots(project)
            image_paths = await generate_shot_images(all_shots, project_dir, project.characters)
            _save_json(project_id, "shot_images.json", image_paths)
            project.status = ProjectStatus.SHOTS_DONE
            _save_project(project)
            # 质量闸门 + 成本记账
            await _assess_and_save_quality(project_id, all_shots, image_paths)
            await _record_usage(project_id, "shots", float(sum(1 for p in image_paths if p)))
        else:
            image_paths = existing_images

        # Step 4: 语音（use_tts 开启才生成；关闭则走原声模式）
        if project.use_tts:
            existing_audio = _load_json(project_id, "audio_paths.json")
            # 验证音频文件是否实际存在
            if existing_audio:
                valid_audio = []
                for a in existing_audio:
                    if isinstance(a, dict):
                        d_ok = a.get("dialogue_audio") and Path(a["dialogue_audio"]).exists()
                        n_ok = a.get("narrator_audio") and Path(a["narrator_audio"]).exists()
                        valid_audio.append({
                            "dialogue_audio": a["dialogue_audio"] if d_ok else None,
                            "narrator_audio": a["narrator_audio"] if n_ok else None,
                        })
                    else:
                        valid_audio.append(a)
                # 检查是否所有需要音频的镜头都有音频
                all_shots = _get_all_shots(project)
                has_all = True
                for i, shot in enumerate(all_shots):
                    if i < len(valid_audio):
                        need_d = shot.dialogues and any(d.line.strip() for d in shot.dialogues)
                        need_n = shot.narrator and shot.narrator.strip()
                        if need_d and not valid_audio[i].get("dialogue_audio"):
                            has_all = False
                        if need_n and not valid_audio[i].get("narrator_audio"):
                            has_all = False
                if has_all:
                    audio_paths = valid_audio
                else:
                    existing_audio = None  # 有缺失，需要重新生成

            if not existing_audio:
                if _is_cancelled(project_id): return
                project.status = ProjectStatus.AUDIO_GENERATING
                _save_project(project)
                all_shots = _get_all_shots(project)
                audio_paths = await generate_all_audio(all_shots, project_dir, project.script.characters)
                _save_json(project_id, "audio_paths.json", audio_paths)
                project.status = ProjectStatus.AUDIO_DONE
                _save_project(project)
            else:
                audio_paths = existing_audio
        else:
            audio_paths = []  # 关闭配音：视频保留原声，不生成 TTS

        # Step 5: AI 视频（已有则跳过，失败则用空值）
        existing_video = _load_json(project_id, "video_paths.json")
        # 验证视频文件是否实际存在
        if existing_video:
            valid_video = []
            for p in existing_video:
                if p and Path(p).exists():
                    valid_video.append(p)
                else:
                    valid_video.append(None)
            # 如果所有视频都存在，才跳过
            if all(p is not None for p in valid_video):
                video_paths = valid_video
            else:
                existing_video = None  # 有缺失，需要重新生成
        
        if not existing_video:
            project.status = ProjectStatus.VIDEO_GENERATING
            _save_project(project)
            all_shots = _get_all_shots(project)
            # 视频生成前预算检查
            if not await _budget_guard(project_id, "video", float(len(all_shots) * 5)):
                return
            try:
                from .engines.video_engine import generate_video_clips
                video_paths = await generate_video_clips(all_shots, image_paths, project_dir, project_id, audio_paths)
            except Exception as e:
                print(f"视频生成失败，跳过: {e}")
                video_paths = [None] * len(image_paths)
            _save_json(project_id, "video_paths.json", video_paths)
            project.status = ProjectStatus.VIDEO_DONE
            _save_project(project)
            await _record_usage(project_id, "video", float(sum(1 for p in video_paths if p) * 5))
        else:
            video_paths = existing_video

        # Step 6: 合成
        project.status = ProjectStatus.COMPOSING
        _save_project(project)
        all_shots = _get_all_shots(project)
        final_video = await compose_final_video(
            shots=all_shots, shot_image_paths=image_paths,
            video_clip_paths=video_paths, audio_paths=audio_paths,
            project_dir=project_dir, use_tts=project.use_tts,
        )
        project.status = ProjectStatus.DONE
        _save_project(project)
        (project_dir / "output" / "result.txt").write_text(final_video, encoding="utf-8")

    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = str(e)
        _save_project(project)


@app.post("/api/projects/{project_id}/generate-all")
async def generate_all_api(project_id: str):
    project = _load_project(project_id)
    if project.status not in [ProjectStatus.CREATED, ProjectStatus.ERROR,
                               ProjectStatus.SCRIPT_DONE, ProjectStatus.CHARACTERS_DONE,
                               ProjectStatus.SHOTS_DONE, ProjectStatus.AUDIO_DONE,
                               ProjectStatus.VIDEO_DONE]:
        if project.status == ProjectStatus.DONE:
            raise HTTPException(status_code=400, detail="项目已完成")
    await _launch_task(project_id, "all", _run_full_pipeline(project_id))
    return {"message": "全流程生成已启动"}


@app.get("/api/projects/{project_id}/result")
async def get_result(project_id: str):
    result_path = OUTPUT_DIR / project_id / "output" / "result.txt"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    return {"video_path": result_path.read_text(encoding="utf-8").strip()}


# ============ 成本 / 任务 / 质量 / 实时预览 增强接口 ============

@app.get("/api/projects/{project_id}/budget")
async def get_budget(project_id: str):
    """查询项目当日成本花费与每日限额"""
    from .engines.cost_engine import get_project_spend
    spent = await get_project_spend(project_id)
    return {"spend": round(spent, 2), "daily_budget": DAILY_BUDGET, "remaining": round(max(DAILY_BUDGET - spent, 0), 2)}


@app.get("/api/projects/{project_id}/task")
async def get_project_task(project_id: str):
    """查询项目当前运行任务（Redis 持久化）"""
    record = await get_task(project_id)
    if not record:
        return {"running": False, "detail": None}
    running = record.get("status") == "running"
    return {"running": running, "detail": record}


@app.get("/api/projects/{project_id}/events")
async def sse_events(project_id: str):
    """SSE 长连接：实时推送该项目日志/进度事件（增量基于 logger 内存缓存）"""
    import json as _json

    async def event_stream():
        # 起始游标：该项目当前已有日志条数
        from .utils import logger as logger_mod
        try:
            all_logs = logger_mod._logs
        except Exception:
            all_logs = []
        cursor = len(all_logs)
        yield "retry: 3000\n\n"
        try:
            while True:
                updated = await wait_log_update(timeout=10.0)
                all_logs = logger_mod._logs
                current = len(all_logs)
                if current < cursor:  # 清空过
                    cursor = 0
                if updated:
                    while cursor < current:
                        log = all_logs[cursor]
                        cursor += 1
                        if log.get("project_id") == project_id:
                            yield f"event: log\ndata: {_json.dumps(log, ensure_ascii=False)}\n\n"
                    yield ": keepalive\n\n"
                else:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def _run_single_shot_redo(project_id: str, index: int):
    """单镜头局部重做：只重生成该镜头的画面/音频/视频并重新合成，其余镜头走缓存"""
    project = _load_project(project_id)
    all_shots = _get_all_shots(project)
    if not all_shots or index >= len(all_shots):
        project.status = ProjectStatus.ERROR
        project.error_message = f"镜头序号 {index} 越界"
        _save_project(project)
        return
    shot = all_shots[index]
    project_dir = OUTPUT_DIR / project_id
    project.status = ProjectStatus.VIDEO_GENERATING  # 复用进行中语义（前端会轮询刷新）
    project.error_message = ""
    _save_project(project)
    add_log("INFO", "redo", f"单镜头重做开始: 镜头 {index}", project_id)
    try:
        # 1) 清除该镜头缓存（图 / 音频 / 视频）
        shot_png = project_dir / "shots" / f"shot_{index:04d}.png"
        shot_png.unlink(missing_ok=True)
        clip_mp4 = project_dir / "video_clips" / f"clip_{index:04d}.mp4"
        clip_mp4.unlink(missing_ok=True)
        audio_dir = project_dir / "audio"
        for f in audio_dir.glob(f"shot_{index:04d}_*.mp3"):
            f.unlink(missing_ok=True)
        # 2) 重生成分镜画面
        from .engines.shot_engine import generate_shot_image_single
        image_path = await generate_shot_image_single(shot, shot_png, project.characters)
        images = _load_json(project_id, "shot_images.json") or []
        if index < len(images):
            images[index] = image_path
        else:
            images.extend([None] * (index - len(images) + 1))
            images[index] = image_path
        _save_json(project_id, "shot_images.json", images)
        # 单镜质量复检
        from .engines.quality_engine import assess_shot_image
        q = await assess_shot_image(shot, index, image_path)
        qualities = _load_json(project_id, "shot_quality.json") or []
        if index < len(qualities):
            qualities[index] = q.model_dump()
        else:
            qualities.extend([None] * (index - len(qualities) + 1))
            qualities[index] = q.model_dump()
        _save_json(project_id, "shot_quality.json", qualities)
        add_log(("SUCCESS" if q.passed else "WARN"), "redo",
                f"镜头 {index} 画面重做完成，质量 {'通过' if q.passed else f'偏低({q.score:.0f}分)'}，得分 {q.score:.0f}", project_id)
        # 3) 重生成该镜头音频（TTS 模式）
        if project.use_tts:
            from .engines.audio_engine import generate_shot_audio
            audio_paths = _load_json(project_id, "audio_paths.json") or []
            if index < len(audio_paths):
                audio_paths[index] = await generate_shot_audio(shot, index, project_dir, project.script.characters)
            _save_json(project_id, "audio_paths.json", audio_paths)
        # 4) 重生成该镜头视频（其余镜头文件已存在会跳过）
        from .engines.video_engine import generate_video_clips
        video_paths = await generate_video_clips(all_shots, images, project_dir, project_id, _load_json(project_id, "audio_paths.json") or [])
        _save_json(project_id, "video_paths.json", video_paths)
        # 5) 重新合成最终视频
        from .engines.compose_engine import compose_final_video
        final_video = await compose_final_video(
            shots=all_shots, shot_image_paths=images,
            video_clip_paths=video_paths,
            audio_paths=_load_json(project_id, "audio_paths.json") or [],
            project_dir=project_dir, use_tts=project.use_tts,
        )
        project.status = ProjectStatus.DONE
        project.error_message = ""
        _save_project(project)
        (project_dir / "output" / "result.txt").write_text(final_video, encoding="utf-8")
        add_log("SUCCESS", "redo", f"镜头 {index} 重做完成，最终视频已重新合成", project_id)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        project.status = ProjectStatus.ERROR
        project.error_message = f"镜头 {index} 重做失败: {str(e)}"
        _save_project(project)
        add_log("ERROR", "redo", f"镜头 {index} 重做失败: {str(e)}", project_id, str(e))


@app.post("/api/projects/{project_id}/shot/{index}/redo")
async def redo_single_shot(project_id: str, index: int):
    """单镜头局部重做（画面+音频+视频，复用其余镜头缓存）"""
    _load_project(project_id)
    if project_id in _running_tasks:
        raise HTTPException(status_code=400, detail="当前有任务运行中，请先停止")
    await _launch_task(project_id, "redo", _run_single_shot_redo(project_id, index))
    return {"message": f"镜头 {index} 重做已启动"}


@app.get("/api/projects/{project_id}/shot/{index}/frame")
async def extract_shot_frame(project_id: str, index: int, at: float = 0.0):
    """视频理解层：抽指定镜头视频的某一帧（默认首帧）做质量/内容核验"""
    from .utils.ffmpeg_utils import extract_frame, probe_duration, probe_has_audio
    clip = OUTPUT_DIR / project_id / "video_clips" / f"clip_{index:04d}.mp4"
    if not clip.exists():
        raise HTTPException(status_code=404, detail="该镜头视频不存在")
    out = OUTPUT_DIR / project_id / "output" / f"clip_{index:04d}_frame_{int(at)}.jpg"
    path = extract_frame(str(clip), str(out), at)
    if not path:
        raise HTTPException(status_code=500, detail="抽帧失败")
    return {
        "frame_path": path,
        "duration": round(probe_duration(str(clip)), 2),
        "has_audio": probe_has_audio(str(clip)),
        "url": f"/static/projects/{project_id}/output/clip_{index:04d}_frame_{int(at)}.jpg",
    }


# ============ 日志 ============

@app.get("/api/logs")
async def get_logs_api(limit: int = 100, project_id: str = ""):
    """获取日志"""
    return get_logs(limit, project_id)


@app.delete("/api/logs")
async def clear_logs_api():
    """清空日志"""
    clear_logs()
    return {"message": "日志已清空"}
