"""FastAPI 主入口 - 小说转漫剧 API"""
import uuid
import json
import shutil
import traceback
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import asyncio
from .config import OUTPUT_DIR, ensure_project_dir
from .models import Project, ProjectCreate, ProjectStatus, Script
from .utils.logger import add_log, get_logs, clear_logs, logger

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


# ============ 项目管理 ============

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    project_id = str(uuid.uuid4())[:8]
    project = Project(id=project_id, name=req.name, novel_text=req.novel_text)
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
    
    return d


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
    task = asyncio.create_task(_run_script_generation(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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
    _load_project(project_id)
    task = asyncio.create_task(_run_character_generation(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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
    task = asyncio.create_task(_run_shot_generation(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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
    _load_project(project_id)
    task = asyncio.create_task(_run_audio_generation(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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
    try:
        image_paths = _load_json(project_id, "shot_images.json") or []
        audio_paths = _load_json(project_id, "audio_paths.json") or []
        video_paths = await generate_video_clips(all_shots, image_paths, OUTPUT_DIR / project_id, project_id, audio_paths)
        project.status = ProjectStatus.VIDEO_DONE
        _save_project(project)
        _save_json(project_id, "video_paths.json", video_paths)
        ok_count = sum(1 for p in video_paths if p)
        add_log("SUCCESS", "video", f"视频生成完成: {ok_count}/{len(all_shots)} 成功", project_id)
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
    task = asyncio.create_task(_run_video_generation(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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
            project_dir=OUTPUT_DIR / project_id,
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
    task = asyncio.create_task(_run_compose(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
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

        # Step 2: 角色（已有则跳过）
        if not project.characters:
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
        else:
            image_paths = existing_images

        # Step 4: 语音（已有则跳过）
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
            try:
                from .engines.video_engine import generate_video_clips
                video_paths = await generate_video_clips(all_shots, image_paths, project_dir, project_id, audio_paths)
            except Exception as e:
                print(f"视频生成失败，跳过: {e}")
                video_paths = [None] * len(image_paths)
            _save_json(project_id, "video_paths.json", video_paths)
            project.status = ProjectStatus.VIDEO_DONE
            _save_project(project)
        else:
            video_paths = existing_video

        # Step 6: 合成
        project.status = ProjectStatus.COMPOSING
        _save_project(project)
        all_shots = _get_all_shots(project)
        final_video = await compose_final_video(
            shots=all_shots, shot_image_paths=image_paths,
            video_clip_paths=video_paths, audio_paths=audio_paths,
            project_dir=project_dir,
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
    task = asyncio.create_task(_run_full_pipeline(project_id))
    _running_tasks[project_id] = task
    task.add_done_callback(lambda _: _running_tasks.pop(project_id, None))
    return {"message": "全流程生成已启动"}


@app.get("/api/projects/{project_id}/result")
async def get_result(project_id: str):
    result_path = OUTPUT_DIR / project_id / "output" / "result.txt"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")
    return {"video_path": result_path.read_text(encoding="utf-8").strip()}


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
