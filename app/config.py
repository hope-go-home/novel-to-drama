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
VOLC_TTS_RESOURCE_ID = os.getenv("VOLC_TTS_RESOURCE_ID", "seed-tts-1.0")

# 通用
IMAGE_STYLE = os.getenv("IMAGE_STYLE", "anime")
VIDEO_DURATION = int(os.getenv("VIDEO_DURATION", "5"))

STYLE_PROMPTS = {
    "anime": "anime style, high quality, detailed, vibrant colors, manga illustration",
    "realistic": "photorealistic, cinematic lighting, detailed, 8k resolution",
    "ink": "chinese ink painting style, watercolor, traditional art, elegant",
    "cyberpunk": "cyberpunk style, neon lights, futuristic, dark atmosphere",
}

def get_style_prefix() -> str:
    return STYLE_PROMPTS.get(IMAGE_STYLE, STYLE_PROMPTS["anime"])

def ensure_project_dir(project_id: str) -> Path:
    project_dir = OUTPUT_DIR / project_id
    for sub in ["characters", "shots", "audio", "video_clips", "output"]:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir
