"""项目配置管理 - 火山引擎"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "projects"))

# 火山引擎 API Key（通用）
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

# 模型
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash-ga-260731")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "doubao-seedream-5-0-260128")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "2K")

# 视频生成（阿里云 DashScope 万相 Wan）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "wan2.7-r2v-2026-06-12")
VIDEO_API_BASE = "https://dashscope.aliyuncs.com"

# 语音合成
VOLC_TTS_APP_ID = os.getenv("VOLC_TTS_APP_ID", "")
VOLC_TTS_ACCESS_TOKEN = os.getenv("VOLC_TTS_ACCESS_TOKEN", "")
VOLC_TTS_RESOURCE_ID = os.getenv("VOLC_TTS_RESOURCE_ID", "seed-tts-2.0")

# 本地音频素材库（音效/环境音/BGM）
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", BASE_DIR / "assets"))
SFX_ENABLED = os.getenv("SFX_ENABLED", "true").lower() == "true"
AMBIENCE_ENABLED = os.getenv("AMBIENCE_ENABLED", "true").lower() == "true"
BGM_ENABLED = os.getenv("BGM_ENABLED", "true").lower() == "true"
SFX_VOLUME = float(os.getenv("SFX_VOLUME", "0.8"))
AMBIENCE_VOLUME = float(os.getenv("AMBIENCE_VOLUME", "0.4"))
BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.22"))
BGM_DUCK = os.getenv("BGM_DUCK", "true").lower() == "true"
# 人声出现时对音效/环境音也做动态闪避（sidechain）
DUCK_SFX_AMB = os.getenv("DUCK_SFX_AMB", "true").lower() == "true"
# BGM 场景之间的交叉淡化时长（秒）
BGM_CROSSFADE = float(os.getenv("BGM_CROSSFADE", "0.4"))
# 合成时是否保留 AI 视频自带的音轨（默认 false：丢弃 i2v 自动生成的 BGM/音效，声音全部由本地素材库提供）
KEEP_VIDEO_AUDIO = os.getenv("KEEP_VIDEO_AUDIO", "false").lower() == "true"
# 是否用画面运动峰值校正音效时刻（把音效吸附到画面"真的在动"的那一下）
SFX_MOTION_ALIGN = os.getenv("SFX_MOTION_ALIGN", "true").lower() == "true"
# 音效吸附窗口（秒）：只在窗口内找到显著运动峰时才吸附
SFX_ALIGN_WINDOW = float(os.getenv("SFX_ALIGN_WINDOW", "0.6"))

# Redis（独立容器 ntd-redis，宿主端口 6381，与 rag/aw 实例隔离）
REDIS_URL = os.getenv("REDIS_URL", "redis://:123456@localhost:6381/0")

# 成本控制：每日预算（元，按单个项目计，key 为 ntd:cost:{日期}:{project_id}），
# 超过时由前端弹窗询问用户是否继续；用户选择继续则照常生成并累计成本，选择停止则本次不启动
DAILY_BUDGET = float(os.getenv("DAILY_BUDGET", "100"))

# 成本价格表（元/单位）
COST_TABLE = {
    "script_per_1k_tokens": float(os.getenv("COST_SCRIPT_PER_1K", "0.01")),   # LLM 每 1K token
    "image_per_image": float(os.getenv("COST_IMAGE", "0.22")),                # Seedream 每张
    "video_per_second": float(os.getenv("COST_VIDEO_SEC", "0.1")),            # 视频每秒（5s≈0.5）
    "tts_per_1k_chars": float(os.getenv("COST_TTS_PER_1K", "0.5")),           # TTS 每 1K 字符
}

# 单镜时长/字数约束（AI 剧本助手 + 语音/视频共用）
# 视频模型单镜上限约 10s，朗读实测约 5~6 字/s；这里按 5 字/s、留 0.5s 余量
SHOT_MAX_SEC = float(os.getenv("SHOT_MAX_SEC", "9.5"))
SHOT_MAX_CHARS = int(os.getenv("SHOT_MAX_CHARS", "45"))

# 通用
IMAGE_STYLE = os.getenv("IMAGE_STYLE", "anime")
VIDEO_DURATION = int(os.getenv("VIDEO_DURATION", "5"))
# 生图参考图：是否把角色设定图裁成"半身"再作参考（避免模型照抄全身站姿/白底构图）
IMAGE_REF_BUST_CROP = os.getenv("IMAGE_REF_BUST_CROP", "true").lower() == "true"

STYLE_PROMPTS = {
    "anime": "anime style, high quality, detailed, vibrant colors, manga illustration",
    "cinematic": "cinematic film still, dramatic volumetric lighting, shallow depth of field, epic composition, movie quality, film grain",
    "realistic": "photorealistic, cinematic lighting, film grain, shallow depth of field, 8k, ultra detailed",
    "ink": "chinese ink painting style, watercolor, traditional art, elegant",
    "guofeng": "chinese guofeng illustration, elegant oriental aesthetics, detailed hanfu, ink wash accents, cinematic, high quality",
    "cyberpunk": "cyberpunk style, neon lights, futuristic, dark atmosphere, blade runner vibes, volumetric fog",
    "3d": "3d render, pixar style, octane render, subsurface scattering, cinematic lighting, highly detailed",
    "korean": "korean webtoon style, clean lineart, soft shading, beautiful character design, high quality",
    "watercolor": "watercolor illustration, soft colors, painterly, delicate, artistic",
    "comic": "american comic style, bold ink lines, dynamic posing, dramatic shading, high contrast",
}

def get_style_prompt(style_key: str = None) -> str:
    """按风格 key 取风格提示词；未指定则用全局 IMAGE_STYLE"""
    key = style_key or IMAGE_STYLE or "anime"
    return STYLE_PROMPTS.get(key, STYLE_PROMPTS["anime"])

def get_style_prefix() -> str:
    return get_style_prompt(IMAGE_STYLE)

def list_styles() -> list:
    """列出所有可用风格（供前端选择）"""
    return [{"key": k, "prompt": v} for k, v in STYLE_PROMPTS.items()]

def ensure_project_dir(project_id: str) -> Path:
    project_dir = OUTPUT_DIR / project_id
    for sub in ["characters", "shots", "audio", "video_clips", "output"]:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir
