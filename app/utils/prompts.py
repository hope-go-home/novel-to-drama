"""LLM Prompt 模板"""

SCRIPT_SYSTEM_PROMPT = """你是一位专业的影视编剧，擅长将小说改编为分镜剧本。
你需要：
1. 深入理解小说的情节、人物关系和情感基调
2. 将叙述性文字转化为可视化的画面描述
3. 为每个镜头规划合适的景别和镜头运动
4. 准确标注角色对话的情绪和动作
5. 保持故事节奏，合理分配每个镜头的时长"""

SCRIPT_USER_PROMPT = """请将以下小说片段改编为分镜剧本。

要求：
1. 识别所有角色，给出外貌和性格描述
2. 将小说拆分为若干场景(Scene)，每个场景包含若干镜头(Shot)
3. 每个镜头标注：景别(特写/中景/远景/全景)、镜头运动(推/拉/摇/移/固定)
4. 对话标注角色名、台词、情绪、动作（台词为纯台词，去掉引号）
5. 旁白(narrator)智能分配：仅当该镜头“没有对白（纯画面/动作）”或“需要衔接解释”时才写旁白；有对白的镜头不要写旁白，narrator 留空字符串
6. 镜头时长规则：duration = max(2.5, (本镜台词总字数 + 旁白字数) / 3.2) 秒，硬上限 9 秒；若按此估算将超过 9 秒，必须拆成新镜头
7. 为每个镜头生成适合AI绘画的画面描述(image_prompt)，英文，必须描述**动作发生的瞬间**（如"剑劈下的一刹那"、"血从掌心涌出"、"剑插入石壁的瞬间"），禁止描述静态站姿/站定不动；包含场景、人物动态、肢体动作、表情、光影、运动模糊
8. 为每个镜头生成适合AI视频的运动描述(video_prompt)，英文，必须以**动作动词开头**（如"swords clash"、"blood erupts"、"the boy charges forward"），描述画面内的动态变化、角色肢体运动、镜头运动、环境变化；若该镜头有对白，必须体现"哪个角色在说话、说出的台词情绪、对应动作与口型"，便于视频画面贴合配音
9. 每个镜头标注 characters 字段，列出画面中出现的所有角色名
10. 镜头数量由切镜规则自然决定，宁少勿滥，并以字数作防失控上限：≤500字≤8镜；500–1200字≤10–12镜；1200–2500字≤14–16镜；2500字以上≤18镜
11. 切镜（必须开新镜头）：场景/时间/地点变化、新人物开口说话、大动作切换（打斗/奔跑/突转等）、本镜时长将超 9 秒
12. 禁止碎切：同一角色连续对话且无动作变化不切、同一机位连贯动作不切、严禁一句话一个镜头、严禁无新信息的重复画面
13. description(desc)：动作/神态/环境画面描述，不用于朗读；对白只放 dialogues 里
14. 每个镜头给出 sound_effects 音效标注数组，元素含四个字段：name(音效名)、start(相对本镜头的起始秒)、end(结束秒)、vol(音量，默认-6dB)；没有音效则为空数组 []。音效 name 必须从下面这份候选列表里挑最贴切的（不要自造词；确实没有合适的就不放该音效）：
候选音效：{sfx_catalog}
15. 每个场景给出 bgm 字段(背景音乐情绪)，必须从固定列表选择一个：悬疑/紧张/危险/冲突/悲伤/温馨/搞笑/轻松/燃/浪漫
16. 每个场景给出 ambience 字段(场所环境音，一句话描述)：如“夜晚虫鸣、风声”“室内安静、远处人声”“街道车流”；没有则留空字符串
17. 节奏硬要求：开场第一个镜头必须直接抛出冲突/悬念/爽点(3秒钩子)，禁止铺垫；每个场景至少一次反转或信息揭露；每个场景结尾停在冲突最高点(卡点)；台词用短句、去水词

小说文本：
---
{novel_text}
---

严格按以下JSON格式输出，不要有多余文字：
{{
  "title": "作品标题",
  "characters": [
    {{
      "name": "角色名",
      "description": "详细外貌描述，包含发型、服装、体型、年龄等",
      "personality": "性格特点",
      "voice_style": "语音风格描述，如：温柔、低沉、活泼等"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "location": "场景地点",
      "time": "时间(白天/夜晚/黄昏等)",
      "mood": "氛围(紧张/温馨/悲伤等)",
      "bgm": "悬疑",
      "ambience": "夜晚虫鸣、风声",
      "shots": [
        {{
          "shot_number": 1,
          "shot_type": "中景",
          "camera": "固定",
          "characters": ["角色名1", "角色名2"],
          "description": "画面内容描述(中文)",
          "dialogues": [
            {{
              "character": "角色名",
              "line": "台词内容",
              "emotion": "情绪",
              "action": "动作"
            }},
            {{
              "character": "角色名2",
              "line": "第二段台词",
              "emotion": "情绪",
              "action": "动作"
            }}
          ],
          "narrator": "",
          "duration": 4.0,
          "sound_effects": [
            {{
              "name": "拔剑出鞘",
              "start": 0.0,
              "end": 1.2,
              "vol": "-6dB"
            }}
          ],
          "image_prompt": "English prompt for image generation: scene description, character appearance, action, lighting, mood, style",
          "video_prompt": "English prompt for video generation: describe the motion and camera movement in the scene"
        }}
      ]
    }}
  ]
}}"""


CHARACTER_VIEW_PROMPT = """Generate a character design reference image.
Character: {name}
Description: {description}
Style: {style}

View angle: {view_angle}
Requirements:
- Full body character sheet
- Clean white/transparent background
- Consistent character design
- High quality, detailed
- {view_specific}"""


SHOT_IMAGE_PROMPT = """Scene description: {description}
Style: {style}
Quality: masterpiece, best quality, highly detailed
Lighting: {lighting}
Mood: {mood}
{extra}"""


VIDEO_MOTION_PROMPT = """Scene: {description}
Camera movement: {camera}
Motion: gentle, smooth animation
Duration: {duration} seconds"""


# 情绪对应的语音参数
EMOTION_VOICE_MAP = {
    "平静": {"speed": 1.0, "pitch": 0, "volume": 0},
    "开心": {"speed": 1.1, "pitch": 2, "volume": 5},
    "悲伤": {"speed": 0.9, "pitch": -2, "volume": -5},
    "愤怒": {"speed": 1.2, "pitch": 3, "volume": 10},
    "恐惧": {"speed": 1.1, "pitch": 1, "volume": -5},
    "紧张": {"speed": 1.15, "pitch": 1, "volume": 5},
    "温柔": {"speed": 0.95, "pitch": -1, "volume": -5},
    "冷漠": {"speed": 0.9, "pitch": -2, "volume": 0},
    "激动": {"speed": 1.25, "pitch": 3, "volume": 10},
}
