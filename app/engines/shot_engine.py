"""分镜画面引擎 - 分镜脚本 → 生成场景画面
使用 Seedream 生图模型（支持图生图）
"""
import io
import httpx
import asyncio
import base64
from pathlib import Path
from PIL import Image
from ..config import (
    ARK_API_KEY, ARK_BASE_URL, IMAGE_MODEL, IMAGE_SIZE, get_style_prompt,
    IMAGE_REF_BUST_CROP,
)
from ..models import Shot, CharacterViews


def _image_to_base64(image_path: str, bust_crop: bool = False) -> str:
    """将图片文件转为 base64 data URI。
    bust_crop=True：裁成"头部+上半身"再作参考，避免模型照抄全身站姿与白底构图。
    """
    path = Path(image_path)
    if not path.exists():
        return ""
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return ""
    if bust_crop:
        w, h = img.size
        # 只取"头部+肩部"（避开张开的双臂/全身姿势），避免模型照抄参考站姿
        box = (int(w * 0.30), 0, int(w * 0.70), int(h * 0.35))
        img = img.crop(box)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{data}"


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
    style_key: str = None,
) -> str:
    """为分镜构建图像生成 prompt：动作/构图放最前，角色外貌只做锚定，明确禁止照抄参考图姿势。"""
    style = get_style_prompt(style_key)
    prompt_parts = []

    # ① 动作/画面（最优先，模型注意力最高）
    if shot.image_prompt:
        prompt_parts.append(shot.image_prompt)
    elif shot.description:
        prompt_parts.append(shot.description)

    # ② 景别
    shot_type_map = {
        "特写": "extreme close-up shot, face focus",
        "中景": "medium shot, waist up",
        "远景": "wide shot, full scene, establishing shot",
        "全景": "full body shot, environmental portrait",
    }
    if shot.shot_type in shot_type_map:
        prompt_parts.append(shot_type_map[shot.shot_type])

    # ③ 风格
    prompt_parts.append(style)

    # ④ 角色外貌（锚定长相/服装，简短放后）
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
                prompt_parts.append(f"character {char_name} appearance (keep face and outfit consistent): {char_desc}")

    # ⑤ 动态要求 + 禁止照抄参考图姿势/背景
    prompt_parts.append(
        "dynamic action pose following the described action and camera angle, "
        "energetic composition, motion in the scene, "
        "do NOT copy the pose, framing or white background of any reference image; "
        "only keep the character's face and outfit consistent"
    )

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
    style_key: str = None,
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

        # 收集角色正面图作为参考图（默认裁成半身，避免照抄全身站姿）
        reference_images = []
        if character_views and shot_characters:
            for char_name in shot_characters:
                for cv in character_views:
                    if cv.character_name == char_name and cv.front_image:
                        ref_b64 = _image_to_base64(cv.front_image, bust_crop=IMAGE_REF_BUST_CROP)
                        if ref_b64:
                            reference_images.append(ref_b64)
                        break

        prompt = build_shot_image_prompt(shot, character_views or [], style_key)

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
    style_key: str = None,
) -> str:
    """生成单张分镜画面"""
    all_character_names = [cv.character_name for cv in character_views] if character_views else []
    shot_characters = _get_shot_characters(shot, all_character_names)

    reference_images = []
    if character_views and shot_characters:
        for char_name in shot_characters:
            for cv in character_views:
                if cv.character_name == char_name and cv.front_image:
                    ref_b64 = _image_to_base64(cv.front_image, bust_crop=IMAGE_REF_BUST_CROP)
                    if ref_b64:
                        reference_images.append(ref_b64)
                    break

    prompt = build_shot_image_prompt(shot, character_views or [], style_key)
    return await _generate_shot_image(prompt, output_path, reference_images)
