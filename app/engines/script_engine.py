"""剧本改写引擎 - 小说文本 → 结构化分镜剧本
使用豆包方舟平台 LLM
"""
import asyncio
import json
import httpx
from ..config import ARK_API_KEY, ARK_BASE_URL, LLM_MODEL, ASSETS_DIR
from ..models import Script
from ..utils.prompts import SCRIPT_SYSTEM_PROMPT, SCRIPT_USER_PROMPT


def _sfx_catalog() -> str:
    """从本地音效映射表取出候选音效名（按素材去重），供 LLM 约束音效命名"""
    try:
        m = json.loads((ASSETS_DIR / "audio_map.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    seen = {}
    for k, v in (m.get("sfx") or {}).items():
        if v not in seen:
            seen[v] = k
    return "、".join(seen.values())


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
            {"role": "user", "content": SCRIPT_USER_PROMPT.format(
                novel_text=novel_text, sfx_catalog=_sfx_catalog())},
        ],
        "temperature": 0.7,
        "max_tokens": 8000,
    }

    # 超时拉长 + 自动重试（LLM 生成长文本有时超过 120s，或网络瞬时抖动）
    async with httpx.AsyncClient(timeout=300.0) as client:
        last_err = None
        for attempt in range(3):
            try:
                response = await client.post(
                    f"{ARK_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                break
            except httpx.HTTPError as e:
                last_err = e
                if attempt == 2:
                    raise
                await asyncio.sleep(3 * (attempt + 1))
        else:
            raise last_err

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
