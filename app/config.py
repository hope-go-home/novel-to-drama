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

# Redis（独立容器 ntd-redis，宿主端口 6381，与 rag/aw 实例隔离）
REDIS_URL = os.getenv("REDIS_URL", "redis://:123456@localhost:6381/0")

# 质量评估：是否启用 LLM 语义一致性打分（会消耗 token，受成本控制）
ENABLE_LLM_QUALITY = os.getenv("ENABLE_LLM_QUALITY", "true").lower() in ("1", "true", "yes")

# 成本控制：每日预算（元，全项目合计），超过时由前端弹窗询问用户是否继续；
# 用户选择继续则照常生成并累计成本，选择停止则本次不启动
DAILY_BUDGET = float(os.getenv("DAILY_BUDGET", "100"))

# 成本价格表（元/单位）
COST_TABLE = {
    "script_per_1k_tokens": float(os.getenv("COST_SCRIPT_PER_1K", "0.01")),   # LLM 每 1K token
    "image_per_image": float(os.getenv("COST_IMAGE", "0.22")),                # Seedream 每张
    "video_per_second": float(os.getenv("COST_VIDEO_SEC", "0.1")),            # 视频每秒（5s≈0.5）
    "tts_per_1k_chars": float(os.getenv("COST_TTS_PER_1K", "0.5")),           # TTS 每 1K 字符
}

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
