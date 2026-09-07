"""语音合成引擎 - 剧本对话/旁白 → 音频文件
使用 Doubao-语音合成大模型 2.0（doubao-speech 官方库）
"""
import asyncio
import re
from pathlib import Path
from ..config import VOLC_TTS_APP_ID, VOLC_TTS_ACCESS_TOKEN, VOLC_TTS_RESOURCE_ID
from ..models import Shot, CharacterInfo
from ..utils.prompts import EMOTION_VOICE_MAP

# 可用音色库（seed-tts-2.0 已验证可用的音色）
VOICE_PRESETS = {
    # 女性音色
    "female_young": "ICL_uranus_zh_female_chunzhenshaonv_tob",      # 纯真少女
    "female_gentle": "zh_female_tianmeiyueyue_uranus_bigtts",       # 甜美玥玥
    "female_intellectual": "zh_female_zhixingnv_uranus_bigtts",     # 知性女
    "female_charming": "zh_female_chanmeinv_uranus_bigtts",         # 妩媚女
    "female_mature": "zh_female_cancan_uranus_bigtts",              # 灿灿（成熟）

    # 男性音色
    "male_young": "saturn_zh_male_shuanglangshaonian_tob",         # 爽朗少年
    "male_academic": "ICL_uranus_zh_male_xuebanantongzhuo_tob",     # 学霸同桌
    "male_cold": "ICL_uranus_zh_male_lengmonanyou_tob",            # 冷漠男友
    "male_rough": "ICL_uranus_zh_male_cujingnansheng_tob",          # 粗犷男声
    "male_clingy": "ICL_uranus_zh_male_nianrennanyou_tob",          # 黏人男友
    "male_yandere": "ICL_uranus_zh_male_bingjiaonanyou_tob",        # 病娇男友
    "male_deep": "ICL_uranus_zh_male_guiyishenmi_tob",             # 诡异神秘

    "narrator": "zh_female_cancan_uranus_bigtts",                  # 旁白
}

# 角色描述关键词 → 音色类型映射
VOICE_KEYWORDS = {
    # 女性
    "female_gentle": ["温柔", "甜美", "恬静", "文静", "淑女", "柔弱", "纤细", "玥玥"],
    "female_intellectual": ["知性", "干练", "精英", "职业", "成熟女性", "御姐", "高管"],
    "female_charming": ["妩媚", "妖娆", "性感", "风情", "迷人", "魅惑", "冷艳"],
    "female_mature": ["成熟", "稳重", "大姐", "老妇", "母亲", "中年女"],
    "female_young": ["年轻", "少女", "活泼", "可爱", "纯真", "小姑娘", "丫头", "小女孩"],

    # 男性（性格特征类，不含年龄词）
    "male_academic": ["学霸", "书呆子", "眼镜", "文弱", "学生", "校园", "同桌", "书生"],
    "male_cold": ["冷漠", "高冷", "冷酷", "寡言", "面瘫", "神秘", "冷淡", "沉默"],
    "male_rough": ["粗犷", "豪迈", "莽夫", "壮汉", "魁梧", "彪悍", "阳刚", "壮"],
    "male_clingy": ["黏人", "粘人", "撒娇", "可爱男", "奶狗"],
    "male_yandere": ["病娇", "偏执", "占有欲", "极端", "疯狂"],
    "male_young": ["阳光", "帅气", "小伙子", "爽朗", "少年", "青年", "二十", "小鲜肉", "活力"],
    "male_deep": ["沧桑", "佝偻", "七十", "八十", "九十", "白发", "诡异", "阴森", "邪气"],
}

# 年龄判断：明确数字年龄最优先，其次是年龄特征词
AGE_RULES = {
    # 明确年龄数字（最高优先级）
    "age_old_num": ["七十", "八十", "九十", "耄耋", "古稀"],
    "age_mid_num": ["四十", "五十", "六十", "不惑"],
    "age_young_num": ["十八", "十九", "二十", "三十", "而立"],
    # 年龄特征词（用于没有明确年龄时）
    "male_old": ["老人", "老头", "老翁", "白发苍苍", "苍老", "佝偻", "驼背"],
    "male_middle": ["中年", "壮年", "成熟稳重", "一家之主"],
    "male_young": ["少年", "青年", "小伙", "少年气"],
}


def _match_male_trait(desc: str, exclude: set = None) -> str:
    """匹配男性性格特征，返回音色 key"""
    best_voice = None
    best_score = 0
    for voice_type, keywords in VOICE_KEYWORDS.items():
        if not voice_type.startswith("male"):
            continue
        if exclude and voice_type in exclude:
            continue
        score = sum(1 for k in keywords if k in desc)
        if score > best_score:
            best_score = score
            best_voice = voice_type
    return best_voice


# 特定角色音色映射（优先级最高）
CHARACTER_VOICE_MAP = {
    "阿福": "ICL_uranus_zh_male_lengmonanyou_tob",      # 冷漠男声
    "老徐头": "ICL_uranus_zh_male_guiyishenmi_tob",     # 诡异神秘男声
}

# 特定类型音色映射（用于年轻女角色等）
TYPE_VOICE_MAP = {
    "young_female": "ICL_uranus_zh_female_chunzhenshaonv_tob",  # 纯真少女
}


def _assign_voice(character_name: str, characters: list[CharacterInfo]) -> str:
    """分配音色：先查特定角色映射，再查手动指定，最后自动判断"""
    # 1. 特定角色音色映射（最高优先级）
    if character_name in CHARACTER_VOICE_MAP:
        return CHARACTER_VOICE_MAP[character_name]

    for char in characters:
        if char.name == character_name:
            # 2. 手动指定优先（voice 字段非空则直接用）
            if char.voice and char.voice.strip():
                return char.voice.strip()

            desc = char.description + " " + char.voice_style + " " + char.name + " " + char.personality
            desc = desc.lower()

            # 判断性别
            male_keywords = ["男", "他", "男声", "阳刚", "胡须", "须发", "青年", "少年", "老头", "老汉", "爷", "叔", "哥", "弟", "公", "伯", "翁", "村长", "汉子", "小伙", "男友", "同桌", "儿"]
            female_keywords = ["女", "她", "女声", "裙", "姑娘", "少女", "小姐", "姐", "妹", "姑", "嫂", "娘", "夫人", "太太", "丫头", "女孩", "女友"]

            is_male = any(w in desc for w in male_keywords)
            is_female = any(w in desc for w in female_keywords)

            if is_male == is_female:
                if any(w in desc for w in ["温柔", "甜美", "漂亮", "美丽", "可爱", "裙", "娘", "小姐"]):
                    is_female = True
                    is_male = False
                elif any(w in desc for w in ["老", "瘦弱", "驼背", "须发", "四十", "五十", "六十", "七十", "八十"]):
                    is_male = True
                    is_female = False
                else:
                    female_name = any(w in character_name for w in ["雨", "雪", "婷", "芳", "丽", "娟", "花", "翠", "秀", "香", "兰", "梅", "子", "玲", "瑶", "妹"])
                    is_female = female_name
                    is_male = not is_female

            # 年轻女角色
            if is_female and any(w in desc for w in ["年轻", "少女", "姑娘", "二十", "活泼", "可爱", "纯真"]):
                return TYPE_VOICE_MAP["young_female"]

            # 男性：先判断年龄段，再匹配性格特征
            if is_male:
                if any(w in desc for w in AGE_RULES["age_old_num"]):
                    return VOICE_PRESETS["male_deep"]
                if any(w in desc for w in AGE_RULES["age_mid_num"]):
                    voice_key = _match_male_trait(desc, exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                if any(w in desc for w in AGE_RULES["age_young_num"]):
                    voice_key = _match_male_trait(desc, exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                if any(w in desc for w in AGE_RULES["male_old"]):
                    return VOICE_PRESETS["male_deep"]
                if any(w in desc for w in AGE_RULES["male_middle"]):
                    voice_key = _match_male_trait(desc, exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                if any(w in desc for w in AGE_RULES["male_young"]):
                    voice_key = _match_male_trait(desc, exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                voice_key = _match_male_trait(desc) or "male_young"
                return VOICE_PRESETS[voice_key]
            else:
                best_voice = None
                best_score = 0
                for voice_type, keywords in VOICE_KEYWORDS.items():
                    if not voice_type.startswith("female"):
                        continue
                    score = sum(1 for k in keywords if k in desc)
                    if score > best_score:
                        best_score = score
                        best_voice = voice_type
                if best_voice:
                    return VOICE_PRESETS[best_voice]
                return VOICE_PRESETS["female_young"]

    return VOICE_PRESETS["narrator"]


async def _synthesize_speech(
    text: str,
    voice_id: str,
    emotion: str,
    output_path: Path,
) -> str:
    """合成语音（使用 doubao-speech 官方库）"""
    from doubao_speech import synthesize_async

    # 情绪语速映射
    emotion_params = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["平静"])

    await synthesize_async(
        text=text,
        output_path=str(output_path),
        voice=voice_id,
        app_id=VOLC_TTS_APP_ID,
        access_token=VOLC_TTS_ACCESS_TOKEN,
        resource_id=VOLC_TTS_RESOURCE_ID,
        speed_ratio=emotion_params["speed"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return str(output_path)


async def _merge_audio_files(audio_files: list[str], output_path: Path) -> str:
    """合并多个音频文件（顺序拼接）"""
    import subprocess
    try:
        from ..engines.compose_engine import FFMPEG_PATH
    except ImportError:
        import imageio_ffmpeg
        FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

    # 创建临时文件列表
    concat_list = output_path.parent / f"concat_audio_{output_path.stem}.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for af in audio_files:
            f.write(f"file '{Path(af).name}'\n")

    cmd = [
        FFMPEG_PATH, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    concat_list.unlink(missing_ok=True)

    if result.returncode != 0:
        # 回退：返回第一个音频，但打印原因便于排查
        print(f"音频合并失败，退回首段: {result.stderr[-200:]}")
        return audio_files[0]

    return str(output_path)


async def generate_shot_audio(
    shot: Shot,
    shot_index: int,
    project_dir: Path,
    characters: list[CharacterInfo],
) -> dict:
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    result = {"dialogue_audio": None, "narrator_audio": None}

    # 生成所有对话音频（支持多段对话），单段也统一命名为 shot_{i}_dialogue.mp3
    if shot.dialogues:
        final_dialogue = audio_dir / f"shot_{shot_index:04d}_dialogue.mp3"
        speech = [d for d in shot.dialogues if d.line.strip()]

        if len(speech) == 1:
            # 单段：直接生成到统一命名文件
            if final_dialogue.exists():
                result["dialogue_audio"] = str(final_dialogue)
            else:
                d = speech[0]
                voice_id = _assign_voice(d.character, characters)
                result["dialogue_audio"] = await _synthesize_speech(
                    text=d.line,
                    voice_id=voice_id,
                    emotion=d.emotion,
                    output_path=final_dialogue,
                )
        elif len(speech) > 1:
            # 多段：逐段生成（可复用缓存），再合并
            if final_dialogue.exists():
                result["dialogue_audio"] = str(final_dialogue)
            else:
                dialogue_files = []
                for j, d in enumerate(speech):
                    seg_path = audio_dir / f"shot_{shot_index:04d}_dialogue_{j}.mp3"
                    if seg_path.exists():
                        dialogue_files.append(str(seg_path))
                    else:
                        voice_id = _assign_voice(d.character, characters)
                        path = await _synthesize_speech(
                            text=d.line,
                            voice_id=voice_id,
                            emotion=d.emotion,
                            output_path=seg_path,
                        )
                        dialogue_files.append(path)
                result["dialogue_audio"] = await _merge_audio_files(dialogue_files, final_dialogue)

    if shot.narrator and shot.narrator.strip():
        output_path = audio_dir / f"shot_{shot_index:04d}_narrator.mp3"
        # 检查文件是否已存在
        if output_path.exists():
            result["narrator_audio"] = str(output_path)
        else:
            result["narrator_audio"] = await _synthesize_speech(
                text=shot.narrator,
                voice_id=VOICE_PRESETS["narrator"],
                emotion="平静",
                output_path=output_path,
            )

    return result


async def generate_all_audio(
    shots: list[Shot],
    project_dir: Path,
    characters: list[CharacterInfo],
) -> list[dict]:
    results = []
    for i, shot in enumerate(shots):
        audio_info = await generate_shot_audio(shot, i, project_dir, characters)
        results.append(audio_info)
    return results
