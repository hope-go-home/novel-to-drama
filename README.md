# 🎬 小说转漫剧 AI 平台

将网络小说自动转为漫剧短视频的全流程平台：从**剧本改写 → 角色设计 → 分镜画面 → 语音配音 → AI 视频 → 合成出片**，并提供可视化工作台、AI 剧本助手与成本预算。

## ✨ 核心特性

- **全流程自动化**：一键从小说文本产出带字幕、带配音的漫剧视频
- **角色一致性**：分镜画面以角色三视图作参考（图生图），保持人物外观跨镜头一致
- **两种声音方案（项目级开关）**
  - 🎙 **TTS 配音**：对白用角色音色、旁白用旁白音色；丢弃 AI 视频原声，成片干净
  - 🎞 **AI 原声拼接**：保留 AI 视频自带画面与声音直接拼接，跳过配音步骤
- **多段对话**：单个镜头支持多段不同角色的对话，按顺序播放
- **视频时长自适应**：有配音时按"对白+旁白"时长，无配音 4–6 秒；单镜硬上限 10 秒，画面不够时冻结末帧延展
- **智能字幕**：自动将对话与旁白烧录到画面
- **AI 剧本助手**：用自然语言对话修改剧本（带时长硬约束校验），支持**历史对话持久化**，改完可选择性重跑下游步骤
- **单镜重做**：对任一镜头重新生成画面/配音/视频并重新合成，其余镜头复用缓存
- **增量与重建**：点击步骤重跑时弹窗选择「增量补全（跳过已存在）」或「清空重建」，避免浪费
- **缓存与校验**：各步骤产物存在即跳过；文件缺失自动检测并补生成
- **资产管理**：前端可预览并单独删除任意资产（剧本/角色/分镜/音频/视频片段/成片）
- **实时进度**：SSE 推送日志与状态，前端步骤进度条实时刷新
- **成本预算**：内置用量记账与预算阈值提醒（Redis 可选，不可用自动降级）
- **音效 / 环境音 / BGM（本地素材库）**：大模型按剧本判断音效名/场景氛围/BGM 情绪，代码匹配本地素材并自动嵌入（音效对帧、环境音循环、BGM 铺底）；匹配不到自动跳过
- **转场 / 卡点**：镜头间淡入淡出（场景边界更明显），切镜点可放转场音效
- **旁白智能分配**：全程/智能/无三档；智能模式只在无对白镜头才加旁白
- **合成可选轨**：合成时可勾选是否混入 音效/环境音/BGM，不满意可关掉重新合成（成片时间戳版本化，不覆盖）

## 🧱 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 前端 | Vue 3 + Vite |
| AI 编剧 | DeepSeek（火山引擎方舟平台） |
| AI 生图 | Doubao Seedream-5.0（火山引擎） |
| AI 视频 | 阿里云 DashScope 万相 Wan（图生视频） |
| AI 语音 | Doubao TTS（火山引擎语音合成） |
| 视频合成 | FFmpeg（imageio-ffmpeg 内置） |
| 任务/缓存 | Redis（可选）+ 本地文件 |

## 🔄 全流程

```
小说文本
   ↓
🧠 DeepSeek LLM → 结构化剧本（场景 / 镜头 / 多段对话 / 情绪 / 旁白 / 音效标注）
   ↓
🎨 Seedream-5.0 → 角色三视图（正面 / 侧面 / 背面）
   ↓
🖼️ Seedream-5.0 图生图 → 分镜画面（参考角色三视图，16:9）
   ↓
🎬 万相 Wan 图生视频 → AI 动态视频片段（时长随配音自适应，≤10s）
   ↓
🎤 Doubao TTS → 多角色配音（对白 + 旁白，按顺序）
   ↓
🔊 本地素材库 → 音效 / 环境音 / BGM（按剧本情绪与音效名匹配，自动嵌入）
   ↓
🎞️ FFmpeg → 最终合成（字幕 + 四轨混音 + 转场 + 响度归一化）
```

> 声音方案在**创建项目**时选择，也可在项目详情页随时切换（切换后需重跑相关步骤生效）。

## 🚀 快速开始

### 1. 安装依赖

```bash
# 后端
pip install -r requirements.txt

# 前端
cd frontend
npm install
cd ..
```

FFmpeg 通过 `imageio-ffmpeg` 自动提供，无需单独安装。

### 2. 配置环境变量

```bash
cp .env.example .env
```

`.env` 示例：

```env
# 火山引擎方舟平台（LLM + 生图）
ARK_API_KEY=ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LLM_MODEL=deepseek-v4-flash-ga-260731
IMAGE_MODEL=doubao-seedream-5-0-260128

# 视频生成（阿里云 DashScope 万相 Wan）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
VIDEO_MODEL=wan2.7-r2v-2026-06-12

# 语音合成（火山引擎语音技术控制台）
VOLC_TTS_APP_ID=你的AppID
VOLC_TTS_ACCESS_TOKEN=你的AccessToken
VOLC_TTS_RESOURCE_ID=seed-tts-2.0

# Redis（可选，用于任务登记/事件；未配置或不可用会自动降级）
REDIS_URL=redis://:123456@localhost:6381/0

# 通用
OUTPUT_DIR=./projects
IMAGE_STYLE=anime
VIDEO_DURATION=5

# 本地音频素材（音效/环境音/BGM）
SFX_ENABLED=true
AMBIENCE_ENABLED=true
BGM_ENABLED=true
SFX_VOLUME=0.8
AMBIENCE_VOLUME=0.4
BGM_VOLUME=0.12
BGM_DUCK=true
DUCK_SFX_AMB=true
BGM_CROSSFADE=0.4
KEEP_VIDEO_AUDIO=false
SFX_MOTION_ALIGN=true
SFX_ALIGN_WINDOW=0.6
```

> 音频素材放在 `assets/sfx`、`assets/ambience`、`assets/bgm`，映射表在 `assets/audio_map.json`（素材音频不入 git，映射表入库）。

### 3. 启动服务

```bash
# 终端1 - 后端
uvicorn app.main:app --reload --port 8000

# 终端2 - 前端
cd frontend
npm run dev
```

浏览器打开 http://localhost:5173

## 🖥️ 前端页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 项目列表 | `/` | 查看所有项目及状态 |
| 创建项目 | `/create` | 项目名 + 小说文本 + **声音方案选择** + 复用已有角色 |
| 项目详情 | `/project/:id` | 全流程可视化 + 预览 + 资产管理 + AI 助手 |

**项目详情页**

- 步骤进度条（剧本 → 角色 → 分镜 → 语音 → 视频 → 合成），点击可重跑（弹窗选择增量 / 重建）
- 剧本预览（场景折叠、多段对话、情绪、旁白、时长、音效标注）
- 角色三视图、分镜画面、语音、AI 视频片段、最终视频，均可在线预览与删除
- AI 剧本助手抽屉：自然语言改剧本、历史对话、应用修改后选择性重跑下游
- 单镜「↻ 重做此镜」：只重做该镜并重新合成

## 🔌 API 接口

### 项目

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | POST | 创建项目 |
| `/api/projects` | GET | 项目列表 |
| `/api/projects/{id}` | GET | 项目详情（含图片/音频/视频路径与校验） |
| `/api/projects/{id}/settings` | POST | 更新项目设置（如 `use_tts`） |
| `/api/projects/{id}/stop` | POST | 停止当前任务 |
| `/api/projects/{id}` | DELETE | 删除项目 |
| `/api/projects/{target}/import-characters/{source}` | POST | 从其它项目导入角色 |

### 生成流程

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects/{id}/generate-all` | POST | 一键生成全流程 |
| `/api/projects/{id}/generate-script` | POST | 生成剧本 |
| `/api/projects/{id}/generate-characters` | POST | 生成角色三视图 |
| `/api/projects/{id}/generate-shots` | POST | 生成分镜画面 |
| `/api/projects/{id}/generate-audio` | POST | 生成语音 |
| `/api/projects/{id}/generate-videos` | POST | 生成 AI 视频 |
| `/api/projects/{id}/generate-audiofx` | POST | 生成音效/环境音/BGM 轨 |
| `/api/projects/{id}/compose` | POST | 合成最终视频（body 可选 `with_bgm/with_sfx/with_ambience`） |
| `/api/projects/{id}/shot/{index}/redo` | POST | 单镜重做 |
| `/api/projects/{id}/result` | GET | 获取最终视频路径 |
| `/api/projects/{id}/outputs` | GET | 历史成片列表 |
| `/api/projects/{id}/task` | GET | 当前任务状态 |
| `/api/projects/{id}/budget` | GET | 成本预算/用量 |
| `/api/projects/{id}/events` | GET | SSE 实时日志/进度 |

### AI 剧本助手

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects/{id}/chat` | POST | 对话式生成剧本修改建议（含历史上下文） |
| `/api/projects/{id}/script/apply` | POST | 应用修改后的剧本（自动备份旧版） |

### 资产删除

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects/{id}/script` | DELETE | 删除剧本 |
| `/api/projects/{id}/characters` | DELETE | 删除角色设计 |
| `/api/projects/{id}/shots` | DELETE | 删除全部分镜 |
| `/api/projects/{id}/audio` | DELETE | 删除全部语音 |
| `/api/projects/{id}/videos` | DELETE | 删除全部视频片段 |
| `/api/projects/{id}/output` | DELETE | 删除最终视频 |
| `/api/projects/{id}/shot/{index}` | DELETE | 删除单张分镜 |
| `/api/projects/{id}/video/{index}` | DELETE | 删除单个视频片段 |

完整 API 文档：http://localhost:8000/docs

## 📁 项目结构

```
novel-to-drama/
├── app/                          # 后端
│   ├── main.py                   # FastAPI 入口 + 路由 + 静态服务
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型（Shot/Scene/Script/Project...）
│   ├── engines/                  # AI 引擎
│   │   ├── script_engine.py      # 剧本改写（DeepSeek LLM）
│   │   ├── chat_engine.py        # AI 剧本助手（对话式改写 + 约束校验）
│   │   ├── character_engine.py   # 角色三视图（Seedream，含缓存）
│   │   ├── shot_engine.py        # 分镜画面（Seedream 图生图，16:9）
│   │   ├── audio_engine.py       # 语音合成（Doubao TTS，多段对话合并）
│   │   ├── audio_fx_engine.py    # 音效/环境音/BGM（本地素材库匹配 + ffmpeg 嵌入）
│   │   ├── video_engine.py       # AI 视频（万相 Wan，时长自适应）
│   │   ├── compose_engine.py     # 最终合成（FFmpeg，字幕 + 四轨混音 + 转场 + 响度）
│   │   └── cost_engine.py        # 成本记账/预算
│   └── utils/
│       ├── prompts.py            # LLM Prompt 模板
│       ├── script_validator.py   # 剧本结构与时长约束校验
│       ├── logger.py             # 日志管理
│       ├── ffmpeg_utils.py       # FFmpeg 封装
│       ├── file_utils.py         # 文件工具
│       ├── event_bus.py          # 事件总线（SSE）
│       ├── task_registry.py      # 任务登记
│       └── redis_client.py       # Redis 客户端（可选，自动降级）
├── frontend/                     # 前端（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/index.js          # API 请求封装
│   │   ├── router.js             # 路由配置
│   │   ├── pages/
│   │   │   ├── Home.vue          # 项目列表
│   │   │   ├── Create.vue        # 创建项目
│   │   │   └── Project.vue       # 项目详情（工作台 + AI 助手）
│   │   ├── components/
│   │   │   └── LogPanel.vue      # 日志面板
│   │   ├── App.vue / main.js / style.css
│   ├── vite.config.js
│   └── package.json
├── assets/                       # 本地音频素材库（音频不入 git）
│   ├── sfx/                      # 音效（拔剑/脚步/开门…）
│   ├── ambience/                 # 环境音（雨/风/夜/街道/室内…）
│   ├── bgm/                      # 背景音乐（按情绪）
│   └── audio_map.json            # 名称/场景/情绪 → 素材 映射表
├── projects/                     # 项目数据（自动生成，不提交 git）
│   └── {project_id}/
│       ├── project.json          # 元数据 + 剧本
│       ├── script_backup.json    # AI 修改前的剧本备份
│       ├── characters/           # 角色三视图
│       ├── shots/                # 分镜画面
│       ├── audio/                # 语音文件
│       ├── sfx/                  # 每镜头音效轨
│       ├── ambience/             # 每镜头环境音轨
│       ├── bgm/                  # 整片 BGM
│       ├── audio_tracks.json     # 音效/环境音/BGM 登记
│       ├── video_clips/          # AI 视频片段
│       └── output/               # 最终合成视频（时间戳版本化）
├── requirements.txt
├── .env.example
└── README.md
```

## 🎨 画面风格

在 `.env` 修改 `IMAGE_STYLE`：

| 值 | 风格 |
|----|------|
| `anime` | 日系动漫风 |
| `realistic` | 写实风格 |
| `ink` | 国风水墨风 |
| `cyberpunk` | 赛博朋克风 |

## 🎙️ 音色分配

**特定角色**优先使用固定音色（保持跨镜头一致），其余角色按描述自动匹配：

| 角色 | 音色 |
|------|------|
| 阿福 | 冷漠男声 |
| 老徐头 | 诡异神秘男声 |
| 旁白 | 灿灿（女声） |

**自动分配规则**（未命中特定角色时）：

- **性别判断**：描述中的性别词（男/女/他/她/叔/娘…）→ 名字特征词兜底
- **男性**：按年龄（老年 → 低沉神秘；中年/青年）+ 性格（冷漠/粗犷/阳光/学霸…）
- **女性**：按性格（温柔/知性/妩媚/成熟/少女纯真…）
- 剧本角色若带 `voice` 字段（可选手动指定音色 ID）则优先使用

## 💰 成本估算

| 环节 | 单价 | 单集(5分钟) |
|------|------|------------|
| 剧本改写 (DeepSeek) | ~¥0.01/1K tokens | ~¥0.5 |
| 角色三视图 (Seedream) | ~¥0.22/张 | ~¥1.3 |
| 分镜画面 (Seedream 图生图) | ~¥0.22/张 | ~¥3 |
| AI视频 (万相 Wan) | ~¥0.5/段(5秒) | ~¥25 |
| 语音合成 (TTS) | ~¥5/万字符 | ~¥1 |
| **合计** | | **~¥31/集** |

> 角色三视图、分镜画面、音频、视频片段均有缓存，重复运行不重复计费。

## 📄 License

MIT
