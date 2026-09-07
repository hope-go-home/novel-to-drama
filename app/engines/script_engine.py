"""剧本改写引擎 - 小说文本 → 结构化分镜剧本
使用豆包方舟平台 LLM
"""
import json
import httpx
from ..config import ARK_API_KEY, ARK_BASE_URL, LLM_MODEL
from ..models import Script
from ..utils.prompts import SCRIPT_SYSTEM_PROMPT, SCRIPT_USER_PROMPT


async def generate_script(novel_text: str) -> Script:
    """将小说文本改写为结构化分镜剧本"""
    if not ARK_API_KEY:
        raise ValueError("未配置 ARK_API_KEY，请在 .env 文件中设置")

    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json",
    }

    if len(novel_text) > 5000:
        novel_text = novel_text[:5000] + "\n...(文本过长，已截取前5000字)"

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
            {"role": "user", "content": SCRIPT_USER_PROMPT.format(novel_text=novel_text)},
        ],
        "temperature": 0.7,
        "max_tokens": 8000,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{ARK_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    result = response.json()
    content = result["choices"][0]["message"]["content"]

    try:
        script_data = json.loads(content)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            script_data = json.loads(json_match.group())
        else:
            raise ValueError(f"LLM 输出无法解析为 JSON:\n{content[:500]}")

    return Script(**script_data)
