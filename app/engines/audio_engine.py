"""语音合成引擎 - 剧本对话/旁白 → 音频文件
使用 Doubao-语音合成大模型 2.0（doubao-speech 官方库）
"""
import asyncio
import re
from pathlib import Path
from ..config import VOLC_TTS_APP_ID, VOLC_TTS_ACCESS_TOKEN, VOLC_TTS_RESOURCE_ID
from ..models import Shot, CharacterInfo
from ..utils.prompts import EMOTION_VOICE_MAP

# 可用音色库（seed-tts-2.0 / ICL 已验证可用的音色）
VOICE_PRESETS = {
    # 女性音色
    "female_young": "ICL_uranus_zh_female_chunzhenshaonv_tob",      # 纯真少女
    "female_gentle": "zh_female_tianmeiyueyue_uranus_bigtts",       # 甜美玥玥
    "female_intellectual": "zh_female_zhixingnv_uranus_bigtts",     # 知性女
    "female_charming": "zh_female_chanmeinv_uranus_bigtts",         # 妩媚女
    "female_mature": "zh_female_cancan_uranus_bigtts",              # 灿灿（成熟）
    "female_wenroumama": "zh_female_wenroumama_uranus_bigtts",      # 温柔妈妈
    "female_jitangmei": "zh_female_jitangmei_uranus_bigtts",        # 鸡汤美（温暖治愈）
    "female_mengyatou": "zh_female_mengyatou_uranus_bigtts",        # 萌丫头
    "female_qiaopinv": "zh_female_qiaopinv_uranus_bigtts",          # 俏皮女
    "female_shaoergushi": "zh_female_shaoergushi_uranus_bigtts",    # 少儿故事
    "female_popo": "zh_female_popo_uranus_bigtts",                  # 婆婆
    "female_zhixingwenwan": "ICL_uranus_zh_female_zhixingwenwan_tob",   # 知性温婉
    "female_tianmeihuopo": "ICL_uranus_zh_female_tianmeihuopo_tob",     # 甜美活泼
    "female_nuanxinxuejie": "ICL_uranus_zh_female_nuanxinxuejie_tob",   # 暖心学姐

    # 男性音色
    "male_young": "saturn_zh_male_shuanglangshaonian_tob",         # 爽朗少年
    "male_academic": "ICL_uranus_zh_male_xuebanantongzhuo_tob",     # 学霸同桌
    "male_cold": "ICL_uranus_zh_male_lengmonanyou_tob",            # 冷漠男友
    "male_rough": "ICL_uranus_zh_male_cujingnansheng_tob",          # 粗犷男声
    "male_clingy": "ICL_uranus_zh_male_nianrennanyou_tob",          # 黏人男友
    "male_yandere": "ICL_uranus_zh_male_bingjiaonanyou_tob",        # 病娇男友
    "male_deep": "ICL_uranus_zh_male_guiyishenmi_tob",             # 诡异神秘
    "male_wennuanahu": "zh_male_wennuanahu_uranus_bigtts",          # 温暖阿虎（温暖男声）
    "male_liufei": "zh_male_liufei_uranus_bigtts",                  # 刘飞（青年播讲男声）
    "male_yuanboxiaoshu": "zh_male_yuanboxiaoshu_uranus_bigtts",    # 原播小说（有声书播讲）
    "male_youyoujunzi": "zh_male_youyoujunzi_uranus_bigtts",        # 悠悠君子（儒雅温润）
    "male_zhengzhiqingnian": "ICL_uranus_zh_male_zhengzhiqingnian_tob",  # 正直青年
    "male_xiaosasuixing": "ICL_uranus_zh_male_xiaosasuixing_tob",        # 潇洒随性
    "male_youroubangzhu": "ICL_uranus_zh_male_youroubangzhu_tob",        # 优柔帮主
    "male_nuanxintitie": "ICL_uranus_zh_male_nuanxintitie_tob",          # 暖心体贴
    "male_lvchaxiaoge": "ICL_uranus_zh_male_lvchaxiaoge_tob",            # 绿茶小哥
    "male_lengdanshuli": "ICL_uranus_zh_male_lengdanshuli_tob",          # 冷淡疏离
    "male_guzhibingjiao": "ICL_uranus_zh_male_guzhibingjiao_tob",        # 固执病娇
}

# 旁白兜底音色（仅当旁白文本无任何风格特征时使用；不再固定某一角色/女声，
# 正常情况由 choose_narrator_voice 按旁白文本风格自动匹配）
NARRATOR_FALLBACK = "zh_female_zhixingnv_uranus_bigtts"             # 知性女（中性叙述兜底）

# 单镜配音硬上限（秒）：视频模型时长有限，配音须压进该区间，保证不“配音比画面长”
VOICE_TARGET_SEC = 10.0
# 语速压缩上限：超过该语速仍超时则标记提示（不再无限加速，避免失真）
VOICE_MAX_SPEED = 1.5

# 角色描述关键词 → 音色类型映射
VOICE_KEYWORDS = {
    # 女性
    "female_gentle": ["温柔", "甜美", "恬静", "文静", "淑女", "柔弱", "纤细", "玥玥"],
    "female_intellectual": ["知性", "干练", "精英", "职业", "成熟女性", "御姐", "高管"],
    "female_charming": ["妩媚", "妖娆", "性感", "风情", "迷人", "魅惑", "冷艳"],
    "female_mature": ["成熟", "稳重", "大姐", "老妇", "母亲", "中年女"],
    "female_young": ["年轻", "少女", "活泼", "可爱", "纯真", "小姑娘", "丫头", "小女孩"],
    "female_wenroumama": ["妈妈", "慈母", "母亲", "温柔妈", "贤惠", "疼爱", "母爱", "宝妈", "老妈", "娘亲"],
    "female_jitangmei": ["治愈", "暖心", "鸡汤", "励志", "温暖", "知心姐姐", "正能量", "鼓励"],
    "female_mengyatou": ["呆萌", "软萌", "迷糊", "天然呆", "萌系", "可爱风", "元气少女", "小丫头"],
    "female_qiaopinv": ["俏皮", "古灵精怪", "机灵", "灵动", "调皮", "活泼俏皮", "鬼马", "精灵"],
    "female_shaoergushi": ["童声", "儿童", "小朋友", "故事", "少儿", "幼儿园", "朗读"],
    "female_popo": ["婆婆", "老婆婆", "老奶奶", "祖母", "老太", "外婆", "姥姥", "年迈女性", "慈祥老人", "高龄"],
    "female_zhixingwenwan": ["温婉", "知性温婉", "书卷气", "端庄", "大家闺秀", "涵养", "优雅"],
    "female_tianmeihuopo": ["甜美活泼", "活力", "明媚", "元气满满", "开心果", "灿烂"],
    "female_nuanxinxuejie": ["学姐", "暖心大姐姐", "温柔学姐", "邻家姐姐", "照顾人", "知心姐姐"],

    # 男性（性格特征类，不含年龄词）
    "male_academic": ["学霸", "书呆子", "眼镜", "文弱", "学生", "校园", "同桌", "书生"],
    "male_cold": ["冷漠", "高冷", "冷酷", "寡言", "面瘫", "神秘", "冷淡", "沉默"],
    "male_rough": ["粗犷", "豪迈", "莽夫", "壮汉", "魁梧", "彪悍", "阳刚", "壮"],
    "male_clingy": ["黏人", "粘人", "撒娇", "可爱男", "奶狗"],
    "male_yandere": ["病娇", "偏执", "占有欲", "极端", "疯狂"],
    "male_young": ["阳光", "帅气", "小伙子", "爽朗", "少年", "青年", "二十", "小鲜肉", "活力"],
    "male_deep": ["沧桑", "佝偻", "七十", "八十", "九十", "白发", "诡异", "阴森", "邪气"],
    "male_wennuanahu": ["温暖男", "邻家大哥哥", "踏实", "可靠", "憨厚", "温柔体贴男", "暖男"],
    "male_liufei": ["成熟男声", "沉稳", "播音腔", "主持", "浑厚", "磁性男声"],
    "male_yuanboxiaoshu": ["说书", "评书", "讲故事", "小说播讲", "有声书", "叙述者"],
    "male_youyoujunzi": ["君子", "儒雅", "温润如玉", "谦谦君子", "书卷气", "彬彬有礼", "文质彬彬"],
    "male_zhengzhiqingnian": ["正直", "正气", "刚正", "磊落", "青年才俊", "正义"],
    "male_xiaosasuixing": ["潇洒", "随性", "不羁", "洒脱", "浪子", "痞帅", "玩世不恭"],
    "male_youroubangzhu": ["优柔", "犹豫", "优柔寡断", "帮主", "柔中带刚"],
    "male_nuanxintitie": ["暖心", "体贴", "细心", "温柔体贴", "暖男", "呵护", "无微不至", "贴心", "学长"],
    "male_lvchaxiaoge": ["绿茶", "阳光学弟", "清秀少年", "小奶狗", "温柔少年", "青涩"],
    "male_lengdanshuli": ["疏离", "清冷", "淡漠", "高岭之花", "拒人千里", "冷情"],
    "male_guzhibingjiao": ["固执", "执拗", "偏执", "病娇", "死心眼", "钻牛角尖"],
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


def _match_trait(desc: str, gender_prefix: str = None, exclude: set = None) -> str:
    """在 VOICE_KEYWORDS 中按关键词给描述打分，返回得分最高的音色 key。
    gender_prefix 限定只匹配该性别（'male'/'female'/None 不限）"""
    best_voice = None
    best_score = 0
    for voice_type, keywords in VOICE_KEYWORDS.items():
        if gender_prefix and not voice_type.startswith(gender_prefix):
            continue
        if exclude and voice_type in exclude:
            continue
        score = sum(1 for k in keywords if k in desc)
        if score > best_score:
            best_score = score
            best_voice = voice_type
    return best_voice


def _gender_from_desc(desc: str, name: str) -> str:
    """判断描述/名字对应的性别倾向，返回 'male' / 'female'"""
    male_keywords = ["男", "他", "男声", "阳刚", "胡须", "须发", "青年", "少年", "老头", "老汉", "爷", "叔", "哥", "弟", "公", "伯", "翁", "村长", "汉子", "小伙", "男友", "同桌", "学长", "儿"]
    female_keywords = ["女", "她", "女声", "裙", "姑娘", "少女", "小姐", "姐", "妹", "姑", "嫂", "娘", "夫人", "太太", "丫头", "女孩", "女友", "婆", "奶奶", "妈", "母亲", "外婆", "姥姥", "祖母", "学姐", "学妹"]

    is_male = any(w in desc for w in male_keywords)
    is_female = any(w in desc for w in female_keywords)

    if is_male != is_female:
        return "male" if is_male else "female"

    # 描述无明显性别词 → 用性格倾向词兜底
    if any(w in desc for w in ["温柔", "甜美", "漂亮", "美丽", "可爱", "裙", "娘", "小姐"]):
        return "female"
    if any(w in desc for w in ["老", "瘦弱", "驼背", "须发", "四十", "五十", "六十", "七十", "八十"]):
        return "male"

    # 最后用名字特征词判断
    female_name = any(w in name for w in ["雨", "雪", "婷", "芳", "丽", "娟", "花", "翠", "秀", "香", "兰", "梅", "玲", "瑶", "妹", "姐", "女"])
    return "female" if female_name else "male"


def _assign_voice(character_name: str, characters: list[CharacterInfo]) -> str:
    """全自动分配音色：不写死任何"角色→音色"绑定，完全依据剧本给角色的
    voice 字段（可选手动）/ 描述 / 音色风格 / 性格 关键词自动匹配。
    """
    # 1. 手动指定（来自剧本数据的 voice 字段，留空则自动判断）
    for char in characters:
        if char.name == character_name:
            if char.voice and char.voice.strip():
                return char.voice.strip()

            desc = char.description + " " + char.voice_style + " " + char.name + " " + char.personality
            desc = desc.lower()

            gender = _gender_from_desc(desc, character_name)

            # 男性：年龄优先，其次性格关键词；均未命中用年龄段默认
            if gender == "male":
                if any(w in desc for w in AGE_RULES["age_old_num"]) or any(w in desc for w in AGE_RULES["male_old"]):
                    return VOICE_PRESETS["male_deep"]
                if any(w in desc for w in AGE_RULES["male_middle"]):
                    voice_key = _match_trait(desc, gender_prefix="male", exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                if any(w in desc for w in AGE_RULES["age_young_num"]) or any(w in desc for w in AGE_RULES["male_young"]):
                    voice_key = _match_trait(desc, gender_prefix="male", exclude={"male_deep"}) or "male_young"
                    return VOICE_PRESETS[voice_key]
                # 无明确年龄 → 纯性格关键词匹配
                voice_key = _match_trait(desc, gender_prefix="male") or "male_young"
                return VOICE_PRESETS[voice_key]

            # 女性：性格关键词自动匹配（含"年轻/少女/纯真"→自动命中纯真少女音色）
            voice_key = _match_trait(desc, gender_prefix="female") or "female_young"
            return VOICE_PRESETS[voice_key]

    # 2. 角色不在角色表（极少见）：按名字特征自动判断性别并选默认音色
    gender = _gender_from_desc("", character_name)
    default_key = "male_young" if gender == "male" else "female_young"
    return VOICE_PRESETS[default_key]


def _assign_narrator_voice(narrator_text: str) -> str:
    """旁白音色：不固定某一女声；若旁白文本带明显风格/语气特征则自动匹配对应音色，
    否则使用中性叙述兜底音色。"""
    text = (narrator_text or "").lower()
    # 磁性/沉稳/播音腔 → 刘飞类磁性叙述男声（优先于"低沉"，避免磁性被吞）
    if any(w in text for w in ["磁性", "沉稳", "浑厚", "播音", "声线低沉", "醇厚"]):
        return VOICE_PRESETS["male_liufei"]
    # 低沉/沙哑/苍老的旁白 → 偏男性叙述音色；阴森悬疑 → 诡异神秘
    if any(w in text for w in ["低沉", "沙哑", "苍老", "厚重", "缓慢"]):
        return VOICE_PRESETS["male_deep"]
    if any(w in text for w in ["说书", "评书", "有声书", "播讲", "讲故事"]):
        return VOICE_PRESETS["male_yuanboxiaoshu"]
    if any(w in text for w in ["儒雅", "娓娓道来", "文雅", "文人"]):
        return VOICE_PRESETS["male_youyoujunzi"]
    if any(w in text for w in ["温柔", "舒缓", "柔和"]):
        return VOICE_PRESETS["female_gentle"]
    if any(w in text for w in ["知性", "冷静", "理性", "客观"]):
        return VOICE_PRESETS["female_intellectual"]
    if any(w in text for w in ["温暖", "治愈", "励志"]):
        return VOICE_PRESETS["female_jitangmei"]
    if any(w in text for w in ["激昂", "热血", "紧张", "急促"]):
        return VOICE_PRESETS["female_young"]
    if any(w in text for w in ["童趣", "少儿", "儿童", "童话"]):
        return VOICE_PRESETS["female_shaoergushi"]
    return NARRATOR_FALLBACK


async def _synthesize_speech(
    text: str,
    voice_id: str,
    emotion: str,
    output_path: Path,
    speed: float = None,
) -> str:
    """合成语音（使用 doubao-speech 官方库）

    speed: 语速倍率；None 则按情绪默认语速。1.0=正常，1.25/1.5 为加速（用于压时长）。
    """
    from doubao_speech import synthesize_async

    # 情绪语速映射（默认），speed 显式传入则覆盖
    emotion_params = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["平静"])
    final_speed = float(speed) if speed is not None else float(emotion_params["speed"])

    await synthesize_async(
        text=text,
        output_path=str(output_path),
        voice=voice_id,
        app_id=VOLC_TTS_APP_ID,
        access_token=VOLC_TTS_ACCESS_TOKEN,
        resource_id=VOLC_TTS_RESOURCE_ID,
        speed=final_speed,
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


async def _synth_dialogue(
    speech: list,
    shot_index: int,
    audio_dir: Path,
    characters: list[CharacterInfo],
    speed: float = None,
    force: bool = False,
) -> str:
    """合成一个镜头的全部对白（单段直接合成；多段逐段再合并）。

    speed: 语速倍率（None=按各句情绪默认）；force=True 时忽略缓存强制重合成
    """
    final_dialogue = audio_dir / f"shot_{shot_index:04d}_dialogue.mp3"
    if not force and final_dialogue.exists():
        return str(final_dialogue)

    # 强制重合成时清掉旧缓存（含逐段）
    if force:
        final_dialogue.unlink(missing_ok=True)
        for f in audio_dir.glob(f"shot_{shot_index:04d}_dialogue_*.mp3"):
            f.unlink(missing_ok=True)

    if len(speech) == 1:
        d = speech[0]
        voice_id = _assign_voice(d.character, characters)
        return await _synthesize_speech(
            text=d.line, voice_id=voice_id, emotion=d.emotion,
            output_path=final_dialogue, speed=speed,
        )

    # 多段：逐段合成（可复用缓存），再顺序合并
    dialogue_files = []
    for j, d in enumerate(speech):
        seg_path = audio_dir / f"shot_{shot_index:04d}_dialogue_{j}.mp3"
        if seg_path.exists() and not force:
            dialogue_files.append(str(seg_path))
            continue
        if force:
            seg_path.unlink(missing_ok=True)
        voice_id = _assign_voice(d.character, characters)
        path = await _synthesize_speech(
            text=d.line, voice_id=voice_id, emotion=d.emotion,
            output_path=seg_path, speed=speed,
        )
        dialogue_files.append(path)
    return await _merge_audio_files(dialogue_files, final_dialogue)


async def _synth_narrator(
    narrator: str,
    shot_index: int,
    audio_dir: Path,
    speed: float = None,
    force: bool = False,
) -> str:
    """合成一个镜头的旁白。speed: 语速倍率；force=True 忽略缓存强制重合成"""
    output_path = audio_dir / f"shot_{shot_index:04d}_narrator.mp3"
    if not force and output_path.exists():
        return str(output_path)
    if force:
        output_path.unlink(missing_ok=True)
    return await _synthesize_speech(
        text=narrator,
        voice_id=_assign_narrator_voice(narrator),
        emotion="平静",
        output_path=output_path,
        speed=speed,
    )


def _shot_voice_total(result: dict, base_dir: Path = None) -> float:
    """测量本镜对白+旁白实际总时长（缺失文件按 0 计）"""
    from ..utils.ffmpeg_utils import probe_duration
    total = 0.0
    for key in ("dialogue_audio", "narrator_audio"):
        p = result.get(key)
        if p:
            total += probe_duration(p, base_dir=str(base_dir) if base_dir else None)
    return total


async def generate_shot_audio(
    shot: Shot,
    shot_index: int,
    project_dir: Path,
    characters: list[CharacterInfo],
    project_id: str = "",
) -> dict:
    """为单个镜头合成对白+旁白。

    时长策略：视频模型时长有限，单镜配音尽量压进 VOICE_TARGET_SEC(10s)：
    - 正常语速合成后若总长 ≤10s → 直接返回
    - 超过 → 用 VOICE_MAX_SPEED(1.5) 语速重合成对白+旁白压缩
    - 1.5 仍超 → 保留完整文本，add_log 提示建议拆分（字幕照常，由合成层兜底）
    """
    from ..utils.logger import add_log
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    result = {"dialogue_audio": None, "narrator_audio": None}

    # 第 1 轮：正常语速（speed=None → 各句按情绪默认）合成
    speech = [d for d in (shot.dialogues or []) if d.line.strip()]
    if speech:
        result["dialogue_audio"] = await _synth_dialogue(speech, shot_index, audio_dir, characters, speed=None)
    if shot.narrator and shot.narrator.strip():
        result["narrator_audio"] = await _synth_narrator(shot.narrator, shot_index, audio_dir, speed=None)

    # 留 0.5s 余量：合计达到阈值即触发压缩，避免刚超 10s 边界
    limit = VOICE_TARGET_SEC - 0.5

    # 检查总时长
    total = _shot_voice_total(result, base_dir=project_dir)
    if total > limit:
        # 超过 → 用 1.5 语速重合成压缩（宁可快也不读不完）
        if speech:
            result["dialogue_audio"] = await _synth_dialogue(speech, shot_index, audio_dir, characters, speed=VOICE_MAX_SPEED, force=True)
        if shot.narrator and shot.narrator.strip():
            result["narrator_audio"] = await _synth_narrator(shot.narrator, shot_index, audio_dir, speed=VOICE_MAX_SPEED, force=True)
        total = _shot_voice_total(result, base_dir=project_dir)
        if total > VOICE_TARGET_SEC:
            # 1.5 仍超：保留完整文本 + 前端可见提示（手动拆分需重跑剧本）
            add_log("WARN", "audio",
                    f"镜头 {shot_index} 配音 {total:.1f}s 超上限 {VOICE_TARGET_SEC:.0f}s，语速 1.5 仍难压进，建议将此镜头拆分为多个镜头",
                    project_id)
        else:
            add_log("INFO", "audio",
                    f"镜头 {shot_index} 配音超限，已用 1.5 语速压至 {total:.1f}s", project_id)

    return result


async def generate_all_audio(
    shots: list[Shot],
    project_dir: Path,
    characters: list[CharacterInfo],
    project_id: str = "",
) -> list[dict]:
    results = []
    for i, shot in enumerate(shots):
        audio_info = await generate_shot_audio(shot, i, project_dir, characters, project_id)
        results.append(audio_info)
    return results
