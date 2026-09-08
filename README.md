# 小说转漫剧 AI 平台

将网络小说自动转为漫剧短视频的全流程平台，覆盖剧本改写、角色设计、画面生成、语音合成、AI视频生成全链路。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 前端 | Vue 3 + Vite |
| AI 编剧 | DeepSeek (火山引擎方舟平台) |
| AI 生图 | Doubao Seedream-5.0 (火山引擎) |
| AI 视频 | 阿里云 DashScope 万相 Wan3.0 |
| AI 语音 | Doubao TTS (火山引擎语音合成) |
| 视频合成 | FFmpeg (imageio-ffmpeg 内置) |

## 全流程

```
小说文本
   ↓
🧠 DeepSeek LLM → 结构化剧本（场景/镜头/多段对话/情绪/旁白）
   ↓
🎨 Seedream-5.0 → 角色三视图（正面/侧面/背面）
   ↓
🖼️ Seedream-5.0 图生图 → 分镜画面（参考角色三视图保持一致性）
   ↓
🎬 万相 Wan3.0 → AI 动态视频片段（时长根据配音自动调整）
   ↓
🎤 Doubao TTS → 多角色语音配音（对话+旁白顺序播放）
   ↓
🎞️ FFmpeg → 最终合成漫剧视频（含字幕、环境音）
```

## 核心特性

- **角色一致性**：分镜画面生成时参考角色三视图（图生图），保持人物外观一致
- **多段对话**：一个镜头支持多段不同角色的对话，顺序播放
- **智能配音**：对话用角色音色，旁白用旁白音色，无配音镜头保留视频原声（环境音）
- **视频时长自适应**：AI 视频时长根据配音总时长自动调整，无配音镜头 4-6 秒
- **冻结最后一帧**：视频不够长时冻结最后一帧，不循环播放
- **智能字幕**：自动烧录对话和旁白字幕到画面
- **缓存机制**：角色三视图、分镜画面、音频、视频均已存在则跳过生成
- **文件校验**：删除文件后重新运行会自动检测缺失并重新生成
- **资产管理**：前端支持单独删除任意资产（剧本/角色/分镜/音频/视频片段）

## 快速开始

### 1. 安装依赖

```bash
cd novel-to-drama

# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

FFmpeg 通过 `imageio-ffmpeg` 自动安装，无需单独配置。

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入 API Key：

```bash
cp .env.example .env
```

`.env` 文件内容：

```env
# 火山引擎 API Key（方舟平台，调 LLM/生图）
ARK_API_KEY=ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 模型名称
LLM_MODEL=deepseek-v4-flash-ga-260731
IMAGE_MODEL=doubao-seedream-5-0-260128

# 语音合成（火山引擎语音技术控制台）
VOLC_TTS_APP_ID=你的AppID
VOLC_TTS_ACCESS_TOKEN=你的AccessToken
VOLC_TTS_RESOURCE_ID=seed-tts-2.0

# 视频生成（阿里云 DashScope 万相 Wan）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# 通用配置
OUTPUT_DIR=./projects
IMAGE_STYLE=anime
VIDEO_DURATION=5
```

### 3. 启动服务

**终端1 - 启动后端：**

```bash
uvicorn app.main:app --reload --port 8000
```

**终端2 - 启动前端：**

```bash
cd frontend
npm run dev
```

然后浏览器打开 http://localhost:5173

## 前端页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 项目列表 | `/` | 查看所有项目及状态 |
| 创建项目 | `/create` | 输入项目名 + 粘贴小说文本 |
| 项目详情 | `/project/:id` | 全流程可视化 + 预览 + 资产管理 |

### 项目详情页功能

- **步骤进度条**：实时显示 6 个步骤的执行状态（等待/进行中/完成/出错），点击可重跑
- **剧本预览**：展开查看每个场景的镜头、多段对话、情绪、旁白
- **角色三视图**：展示每个角色的正面/侧面/背面参考图，支持删除
- **分镜画面**：网格展示所有生成的场景画面，支持单张删除
- **语音播放**：逐镜头播放对话和旁白音频，支持删除
- **AI 视频片段**：网格展示所有生成的视频片段，支持单个删除和在线播放
- **最终视频**：在线播放最终合成的漫剧视频 + 下载

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | POST | 创建项目 |
| `/api/projects` | GET | 项目列表 |
| `/api/projects/{id}` | GET | 项目详情（含图片/音频/视频路径） |
| `/api/projects/{id}/generate-all` | POST | 一键生成全流程 |
| `/api/projects/{id}/generate-script` | POST | 生成剧本 |
| `/api/projects/{id}/generate-characters` | POST | 生成角色三视图 |
| `/api/projects/{id}/generate-shots` | POST | 生成分镜画面 |
| `/api/projects/{id}/generate-audio` | POST | 生成语音 |
| `/api/projects/{id}/generate-videos` | POST | 生成 AI 视频 |
| `/api/projects/{id}/compose` | POST | 合成最终视频 |
| `/api/projects/{id}/result` | GET | 获取最终视频路径 |
| `/api/projects/{id}/script` | DELETE | 删除剧本 |
| `/api/projects/{id}/characters` | DELETE | 删除角色设计 |
| `/api/projects/{id}/shots` | DELETE | 删除所有分镜画面 |
| `/api/projects/{id}/audio` | DELETE | 删除所有语音 |
| `/api/projects/{id}/videos` | DELETE | 删除所有视频片段 |
| `/api/projects/{id}/output` | DELETE | 删除最终视频 |
| `/api/projects/{id}/shot/{index}` | DELETE | 删除单张分镜 |
| `/api/projects/{id}/video/{index}` | DELETE | 删除单个视频片段 |

完整 API 文档：http://localhost:8000/docs

## 项目结构

```
novel-to-drama/
├── app/                          # 后端
│   ├── main.py                   # FastAPI 入口 + 静态文件服务
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型
│   ├── engines/                  # AI 引擎
│   │   ├── script_engine.py      # 剧本改写（DeepSeek LLM）
│   │   ├── character_engine.py   # 角色三视图（Seedream 生图，含缓存）
│   │   ├── shot_engine.py        # 分镜画面（Seedream 图生图，参考角色三视图）
│   │   ├── audio_engine.py       # 语音合成（Doubao TTS，多段对话合并）
│   │   ├── video_engine.py       # AI视频生成（万相 Wan，时长自适应配音）
│   │   └── compose_engine.py     # 最终视频合成（FFmpeg，含字幕+环境音）
│   └── utils/
│       ├── prompts.py            # LLM Prompt 模板
│       ├── logger.py             # 日志管理
│       └── file_utils.py         # 文件工具
├── frontend/                     # 前端（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/index.js          # API 请求封装
│   │   ├── router.js             # 路由配置
│   │   ├── pages/
│   │   │   ├── Home.vue          # 项目列表页
│   │   │   ├── Create.vue        # 创建项目页
│   │   │   └── Project.vue       # 项目详情（全流程可视化+资产管理）
│   │   ├── components/
│   │   │   └── LogPanel.vue      # 日志面板组件
│   │   ├── App.vue               # 根组件
│   │   ├── main.js               # 入口
│   │   └── style.css             # 全局样式
│   ├── vite.config.js            # Vite 配置（含 API 代理）
│   └── package.json
├── projects/                     # 项目数据（自动生成，不提交到 git）
│   └── {project_id}/
│       ├── project.json          # 项目元数据+剧本
│       ├── characters/           # 角色三视图
│       ├── shots/                # 分镜画面
│       ├── audio/                # 语音文件
│       ├── video_clips/          # AI 视频片段
│       └── output/               # 最终合成视频
├── requirements.txt
├── .env.example                  # API Key 配置模板
└── README.md
```

## 画面风格

在 `.env` 中修改 `IMAGE_STYLE` 切换风格：

| 值 | 风格 |
|----|------|
| `anime` | 日系动漫风 |
| `realistic` | 写实风格 |
| `ink` | 国风水墨风 |
| `cyberpunk` | 赛博朋克风 |

## 音色分配

不写死任何"角色 → 音色"绑定，全部自动智能判断。

### 自动分配规则

**角色**：根据剧本给角色的描述/音色风格/性格，用关键词自动匹配音色：
- **性别判断**：描述里的性别词（男/女/他/她/叔/娘等）→ 名字特征词兜底
- **男性**：年龄（老年 → 低沉神秘，中年/青年）+ 性格特征（冷漠/粗犷/阳光/学霸等）
- **女性**：性格特征（温柔/知性/妩媚/成熟/少女纯真等）自动命中对应音色
- 剧本角色若带 `voice` 字段（可选手动指定音色 ID）则优先使用，留空全自动

**旁白**：不固定某一女声，依据旁白文本的语气/风格自动匹配：
- 低沉/沙哑/阴森 → 偏男性叙述音色；温柔/舒缓 → 甜美女声；知性/冷静 → 知性女声；激昂/紧张 → 活泼女声
- 无明显风格特征 → 使用中性叙述兜底音色

## 成本估算

| 环节 | 单价 | 单集(5分钟) |
|------|------|------------|
| 剧本改写 (DeepSeek) | ~¥0.01/1K tokens | ~¥0.5 |
| 角色三视图 (Seedream) | ~¥0.22/张 | ~¥1.3 |
| 分镜画面 (Seedream 图生图) | ~¥0.22/张 | ~¥3 |
| AI视频 (万相 Wan) | ~¥0.5/段(5秒) | ~¥25 |
| 语音合成 (TTS) | ~¥5/万字符 | ~¥1 |
| **合计** | | **~¥31/集** |

注：角色三视图和分镜画面已有缓存，重复运行不产生费用。

## 常见问题

**Q: FFmpeg 找不到？**
A: 已通过 `imageio-ffmpeg` 自动安装，无需单独配置。如仍有问题，运行 `pip install imageio[ffmpeg]`。

**Q: 生图/视频 API 报错？**
A: 检查火山引擎账户余额是否充足。Seedream 需要开通模型服务，万相 Wan 需要阿里云 DashScope API Key。

**Q: 语音合成 55000000 错误？**
A: 确认 `VOLC_TTS_RESOURCE_ID` 与音色匹配。`seed-tts-2.0` 适用于大部分音色。

**Q: 视频生成超时？**
A: 视频生成时间取决于时长和复杂度，通常 1-5 分钟。代码会一直等待直到完成。

**Q: 合成视频没有声音？**
A: 检查是否有配音文件生成。无配音的镜头会保留视频原声（环境音）。

**Q: 前端页面空白？**
A: 确保后端已启动（端口 8000），Vite 会自动代理 API 请求。

## License

MIT
