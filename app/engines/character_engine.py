"""角色设计引擎 - 角色描述 → 三视图(正面/侧面/背面)
使用 Seedream 生图模型
"""
import httpx
import base64
from pathlib import Path
from ..config import ARK_API_KEY, ARK_BASE_URL, IMAGE_MODEL, IMAGE_SIZE, get_style_prefix
from ..models import CharacterInfo, CharacterViews


VIEW_ANGLES = {
    "front": "front view, facing the viewer, looking directly at camera, full body",
    "side": "side view, 45 degree angle, three-quarter view, full body",
    "back": "back view, facing away from the camera, full body",
}


async def _generate_image(prompt: str, output_path: Path) -> str:
    """调用 Seedream 生成单张图片"""
    if not ARK_API_KEY:
        raise ValueError("未配置 ARK_API_KEY")

    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "size": IMAGE_SIZE,
        "sequential_image_generation": "disabled",
        "watermark": False,
        "response_format": "url",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{ARK_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        # 获取图片 URL 或 base64
        image_data = result["data"][0]
        if "url" in image_data:
            img_resp = await client.get(image_data["url"])
            img_resp.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_resp.content)
        elif "b64_json" in image_data:
            img_bytes = base64.b64decode(image_data["b64_json"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
        else:
            raise ValueError(f"生图 API 返回格式异常: {result}")

        return str(output_path)


async def generate_character_views(
    character: CharacterInfo,
    project_dir: Path,
) -> CharacterViews:
    """为一个角色生成三视图"""
    char_dir = project_dir / "characters" / character.name
    char_dir.mkdir(parents=True, exist_ok=True)

    # 缓存检查：三视图已存在则跳过
    front_path = char_dir / "front.png"
    side_path = char_dir / "side.png"
    back_path = char_dir / "back.png"
    if front_path.exists() and side_path.exists() and back_path.exists():
        return CharacterViews(
            character_name=character.name,
            description=character.description,
            front_image=str(front_path),
            side_image=str(side_path),
            back_image=str(back_path),
        )

    style = get_style_prefix()
    views = CharacterViews(
        character_name=character.name,
        description=character.description,
    )

    for view_key, view_en in VIEW_ANGLES.items():
        prompt = f"{style}, character design reference sheet, {character.description}, {view_en}, clean white background, high quality, detailed"

        output_path = char_dir / f"{view_key}.png"
        result_path = await _generate_image(prompt, output_path)

        if view_key == "front":
            views.front_image = result_path
        elif view_key == "side":
            views.side_image = result_path
        else:
            views.back_image = result_path

    return views


async def generate_all_characters(
    characters: list[CharacterInfo],
    project_dir: Path,
) -> list[CharacterViews]:
    """为所有角色生成三视图"""
    results = []
    for char in characters:
        views = await generate_character_views(char, project_dir)
        results.append(views)
    return results
