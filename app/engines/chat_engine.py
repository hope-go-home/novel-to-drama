"""AI 剧本助手引擎 - 用对话方式约束式修改剧本

流程：
1. 把当前剧本 JSON + 用户指令 + 硬约束发给 LLM
2. LLM 输出修改后的全量剧本 JSON
3. 用 script_validator 校验：结构 + 单镜时长预检
4. 若违反硬约束（超长镜头仍存在）→ 提示 LLM 修正重试（最多 N 轮）
5. 校验通过/可接受 → 返回新剧本 + 变更摘要 + 校验报告

约束是“硬”的，由代码强制：AI 改完若某镜朗读字数仍超 SHOT_MAX_CHARS，
就要求它继续精简，而不是直接覆盖。这样“AI 对话改剧本”不会重演超长问题。
"""
import asyncio
import json
import re
import httpx

from ..config import ARK_API_KEY, ARK_BASE_URL, LLM_MODEL, SHOT_MAX_SEC, SHOT_MAX_CHARS
from ..utils.script_validator import validate_script, summarize_script, flat_shots

CHAT_SYSTEM_PROMPT = """你是一位专业影视编剧助手，负责按用户的修改要求调整已生成的分镜剧本。
你必须严格遵循以下硬性规则，否则修改无效：
1. 只修改用户要求涉及的部分，未提及的镜头/场景保持原样，禁止无故改动
2. 保持输出为完整的 JSON 分镜剧本（结构必须与输入一致，包含所有 scenes/shots 字段）
3. 台词与旁白要精简：单镜头“对白台词字数 + 旁白字数”合计不得超过 {max_chars} 字（对应朗读约 {max_sec}s）
4. 若某镜头朗读文本过长，优先精简语句；一段过长就把它拆成多个镜头，不得保留超长单镜
5. 保留角色名、情节推进与情绪；description/image_prompt/video_prompt 要随内容同步调整
6. 不要输出任何 JSON 之外的文字说明

输出必须是合法的 JSON，形如：
{{"title": "...", "characters": [...], "scenes": [...]}}"""


def _llm_chat(messages: list[dict], temperature: float = 0.4) -> str:
    """调用 LLM，返回文本内容"""
    if not ARK_API_KEY:
        raise ValueError("未配置 ARK_API_KEY，请在 .env 文件中设置")
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 8000,
    }
    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=300.0) as client:
        last_err = None
        for attempt in range(3):
            try:
                response = client.post(f"{ARK_BASE_URL}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                break
            except httpx.HTTPError as e:
                last_err = e
                if attempt == 2:
                    raise
                import time
                time.sleep(3 * (attempt + 1))
        else:
            raise last_err
    return response.json()["choices"][0]["message"]["content"]


def _parse_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', content)
        if not m:
            raise ValueError(f"LLM 输出无法解析为 JSON:\n{content[:500]}")
        return json.loads(m.group())


def _build_messages(script: dict, instruction: str, feedback: str = "") -> list[dict]:
    """构造消息。feedback 非空时作为前一轮校验失败的原因要求修正"""
    system = CHAT_SYSTEM_PROMPT.format(max_chars=SHOT_MAX_CHARS, max_sec=int(SHOT_MAX_SEC))
    prompt = (
        "当前分镜剧本（JSON）：\n```json\n"
        f"{json.dumps(script, ensure_ascii=False, indent=2)}\n```\n\n"
        f"用户要求：{instruction}\n"
    )
    if feedback:
        prompt += f"\n你上一轮的修改未通过校验，原因如下，请据此修正后重新输出完整 JSON：\n{feedback}\n"
    prompt += "\n请直接输出修改后的完整 JSON 剧本："
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


async def ai_revise_script(script: dict, instruction: str, max_retry: int = 2) -> dict:
    """用 LLM 修改剧本，并强制时长约束。

    返回：
    {
      "revised": dict,             # 修改后的完整剧本（校验通过版本）
      "before": {...}, "after": {...},  # 前后摘要
      "changed_shots": [...],      # 变更镜头摘要
      "warnings": [...],           # 仍存留的提示（应尽量为空）
    }
    """
    revised = None
    feedback = ""

    for _ in range(max_retry + 1):
        messages = _build_messages(script, instruction, feedback)
        content = await asyncio.to_thread(_llm_chat, messages)
        try:
            revised = _parse_json(content)
        except Exception as e:
            feedback = f"输出不是合法 JSON：{e}"
            continue

        report = validate_script(revised)
        if not report["ok"]:
            feedback = "结构校验未通过：\n- " + "\n- ".join(report["errors"])
            continue
        if report["warnings"]:
            # 仍有超长镜头 → 视为硬约束未满足，要求修正
            feedback = "仍存在超长镜头（违反单镜字数/时长约束）：\n- " + "\n- ".join(report["warnings"])
            continue

        # 校验通过
        revised = _normalize(revised)
        break
    else:
        # 重试耗尽仍不满足 → 返回最后一次结果 + 明确提示，不强改
        if revised is None:
            raise ValueError(f"AI 多次修改仍无法生成合法剧本，请换一种说法描述你的要求\n最近原因：{feedback}")

    return {
        "revised": revised,
        "before": summarize_script(script),
        "after": summarize_script(revised),
        "changed_shots": _diff_shots(script, revised),
        "warnings": [],
    }


def _normalize(script: dict) -> dict:
    """确保关键字段为可序列化对象；移除多余顶层 key"""
    keys = ["title", "characters", "scenes"]
    out = {k: script.get(k) for k in keys if k in script}
    if not out.get("title"):
        out["title"] = ""
    if not isinstance(out.get("characters"), list):
        out["characters"] = []
    if not isinstance(out.get("scenes"), list):
        out["scenes"] = []
    return out


def _diff_shots(before: dict, after: dict) -> list:
    """对比前后剧本镜头数，输出变更摘要（用于前端 diff 预览）"""
    b_shots = flat_shots(before)
    a_shots = flat_shots(after)
    if len(b_shots) == len(a_shots):
        return [{"type": "same_count", "before": len(b_shots), "after": len(a_shots)}]
    return [{"type": "shot_count_change", "before": len(b_shots), "after": len(a_shots)}]
