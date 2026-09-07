"""数据模型定义"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ProjectStatus(str, Enum):
    CREATED = "created"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_DONE = "script_done"
    CHARACTERS_GENERATING = "characters_generating"
    CHARACTERS_DONE = "characters_done"
    SHOTS_GENERATING = "shots_generating"
    SHOTS_DONE = "shots_done"
    AUDIO_GENERATING = "audio_generating"
    AUDIO_DONE = "audio_done"
    VIDEO_GENERATING = "video_generating"
    VIDEO_DONE = "video_done"
    COMPOSING = "composing"
    DONE = "done"
    ERROR = "error"


# ============ 剧本相关模型 ============

class Dialogue(BaseModel):
    character: str = Field(default="", description="角色名")
    line: str = Field(default="", description="台词")
    emotion: str = Field(default="平静", description="情绪")
    action: str = Field(default="", description="动作描述")


class Shot(BaseModel):
    shot_number: int
    shot_type: str = Field(description="景别: 特写/中景/远景/全景")
    camera: str = Field(default="固定", description="镜头运动: 推/拉/摇/移/固定")
    description: str = Field(description="画面描述")
    dialogues: list[Dialogue] = Field(default=[], description="对话列表（支持多段对话）")
    narrator: str = Field(default="", description="旁白")
    duration: float = Field(default=3.0, description="时长(秒)")
    image_prompt: str = Field(default="", description="图像生成prompt")
    video_prompt: str = Field(default="", description="视频生成prompt")
    characters: list[str] = Field(default=[], description="画面中出现的角色名列表")


class Scene(BaseModel):
    scene_number: int
    location: str = Field(description="地点")
    time: str = Field(default="", description="时间")
    mood: str = Field(default="", description="氛围")
    shots: list[Shot] = []


class CharacterInfo(BaseModel):
    name: str
    description: str = Field(description="外貌描述")
    personality: str = Field(default="", description="性格")
    voice_style: str = Field(default="", description="语音风格")
    voice: str = Field(default="", description="指定音色 Voice_Type（留空则自动判断）")


class Script(BaseModel):
    title: str = ""
    characters: list[CharacterInfo] = []
    scenes: list[Scene] = []


# ============ 角色三视图相关 ============

class CharacterViews(BaseModel):
    character_name: str
    description: str
    front_image: str = Field(default="", description="正面图路径")
    side_image: str = Field(default="", description="侧面图路径")
    back_image: str = Field(default="", description="背面图路径")


# ============ 项目相关 ============

class ProjectCreate(BaseModel):
    name: str = Field(description="项目名称")
    novel_text: str = Field(description="小说文本")


class Project(BaseModel):
    id: str
    name: str
    novel_text: str
    status: ProjectStatus = ProjectStatus.CREATED
    script: Optional[Script] = None
    characters: list[CharacterViews] = []
    error_message: str = ""
