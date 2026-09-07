"""分镜画面引擎 - 分镜脚本 → 生成场景画面
使用 Seedream 生图模型（支持图生图）
"""
import httpx
import asyncio
import base64
from pathlib import Path
from ..config import ARK_API_KEY, ARK_BASE_URL, IMAGE_MODEL, IMAGE_SIZE, get_style_prefix
from ..models import Shot, CharacterViews


def _image_to_base64(image_path: str) -> str:
    """将图片文件转为 base64 data URI"""
    path = Path(image_path)
    if not path.exists():
        return ""
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    mime = mime_map.get(suffix, "image/png")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _get_shot_characters(shot: Shot, all_character_names: list[str]) -> list[str]:
    """从镜头中提取所有出现的角色名"""
    found = set()
    # 从 dialogues 提取
    if shot.dialogues:
        for d in shot.dialogues:
            if d.character:
                found.add(d.character)
    # 从 shot.characters 提取
    if hasattr(shot, "characters") and shot.characters:
        found.update(shot.characters)
    # 从 description 和 narrator 中匹配已知角色名
    text = shot.description + " " + shot.narrator
    for name in all_character_names:
        if name in text:
            found.add(name)
    return list(found)


def _get_character_description(character_name: str, character_views: list[CharacterViews]) -> str:
    """从角色列表中获取指定角色的外貌描述"""
    for char in character_views:
        if char.character_name == character_name:
            return char.description
    return ""


def build_shot_image_prompt(
    shot: Shot,
    character_views: list[CharacterViews] = None,
) -> str:
    """为分镜构建图像生成 prompt，参考角色设计"""
    style = get_style_prefix()
    prompt_parts = [style]

    # 添加角色外貌描述（如果有）
    if character_views:
        shot_chars = []
        if shot.dialogues:
            for d in shot.dialogues:
                if d.character:
                    shot_chars.append(d.character)
        if hasattr(shot, "characters") and shot.characters:
            shot_chars.extend(shot.characters)
        for char_name in set(shot_chars):
            char_desc = _get_character_description(char_name, character_views)
            if char_desc:
                prompt_parts.append(f"character {char_name}: {char_desc}")

    if shot.image_prompt:
        prompt_parts.append(shot.image_prompt)
    else:
        prompt_parts.append(shot.description)

    shot_type_map = {
        "特写": "extreme close-up shot, face focus",
        "中景": "medium shot, waist up",
        "远景": "wide shot, full scene, establishing shot",
        "全景": "full body shot, environmental portrait",
    }
    if shot.shot_type in shot_type_map:
        prompt_parts.append(shot_type_map[shot.shot_type])

    # 16:9 横向构图，与 AI 视频画幅一致，作首帧不变形
    prompt_parts.append("horizontal 16:9 wide composition, landscape aspect ratio")
    prompt_parts.append("masterpiece, best quality, highly detailed, cinematic lighting")
    return ", ".join(prompt_parts)


async def _generate_shot_image(
    prompt: str,
    output_path: Path,
    reference_images: list[str] = None,
) -> str:
    """调用 Seedream 生成单张分镜画面（支持图生图）"""
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

    # 图生图：传入参考图（角色三视图）
    if reference_images:
        if len(reference_images) == 1:
            payload["image"] = reference_images[0]
        else:
            payload["image"] = reference_images

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{ARK_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

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


async def generate_shot_images(
    shots: list[Shot],
    project_dir: Path,
    character_views: list[CharacterViews] = None,
) -> list[str]:
    """为所有分镜生成画面（图生图模式）"""
    shots_dir = project_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    # 收集所有角色名
    all_character_names = [cv.character_name for cv in character_views] if character_views else []

    results = []
    for i, shot in enumerate(shots):
        # 检查分镜画面是否已存在
        output_path = shots_dir / f"shot_{i:04d}.png"
        if output_path.exists():
            print(f"分镜 {i} 画面已存在，跳过生成")
            results.append(str(output_path))
            continue

        # 提取镜头中的角色
        shot_characters = _get_shot_characters(shot, all_character_names)

        # 收集角色正面图作为参考图
        reference_images = []
        if character_views and shot_characters:
            for char_name in shot_characters:
                for cv in character_views:
                    if cv.character_name == char_name and cv.front_image:
                        ref_b64 = _image_to_base64(cv.front_image)
                        if ref_b64:
                            reference_images.append(ref_b64)
                        break

        prompt = build_shot_image_prompt(shot, character_views or [])

        try:
            mode = "图生图" if reference_images else "文生图"
            print(f"生成分镜 {i} 画面（{mode}）...")
            result = await _generate_shot_image(prompt, output_path, reference_images)
            results.append(result)
            print(f"分镜 {i} 画面完成")
        except Exception as e:
            print(f"分镜 {i} 画面生成失败: {e}")
            results.append(None)

        await asyncio.sleep(1)

    return results


async def generate_shot_image_single(
    shot: Shot,
    output_path: Path,
    character_views: list[CharacterViews] = None,
) -> str:
    """生成单张分镜画面"""
    all_character_names = [cv.character_name for cv in character_views] if character_views else []
    shot_characters = _get_shot_characters(shot, all_character_names)

    reference_images = []
    if character_views and shot_characters:
        for char_name in shot_characters:
            for cv in character_views:
                if cv.character_name == char_name and cv.front_image:
                    ref_b64 = _image_to_base64(cv.front_image)
                    if ref_b64:
                        reference_images.append(ref_b64)
                    break

    prompt = build_shot_image_prompt(shot, character_views or [])
    return await _generate_shot_image(prompt, output_path, reference_images)
