# 🎬 小说转漫剧 AI 平台

将网络小说自动转为漫剧短视频的全流程平台，覆盖剧本改写、角色设计、画面生成、语音合成、AI视频生成全链路。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 前端 | Vue 3 + Vite |
| AI 编剧 | 豆包 DeepSeek-V4-Flash |
| AI 生图 | 豆包 Seedream-5.0 |
| AI 视频 | 豆包 Seedance-1.5-pro |
| AI 语音 | 豆包 Doubao-语音合成 1.0 |
| 视频合成 | FFmpeg |

## 全流程

```
小说文本
   ↓
🧠 DeepSeek-V4-Flash → 结构化剧本（场景/镜头/对话/情绪）
   ↓
🎨 Seedream-5.0 → 角色三视图 + 分镜画面
   ↓
🎬 Seedance-1.5-pro → AI 动态视频片段
   ↓
🎤 Doubao TTS → 多角色语音配音
   ↓
🎞️ FFmpeg → 最终合成漫剧视频
```

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

需要安装 FFmpeg（视频合成必需）：
- Windows: 下载 https://ffmpeg.org/download.html 并添加到 PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入火山引擎 API Key：

```bash
cp .env.example .env
```

`.env` 文件内容：

```env
# 火山引擎 API Key（方舟平台，调 LLM/生图/视频）
ARK_API_KEY=ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# 模型名称（已验证可用的 Model ID）
LLM_MODEL=deepseek-v4-flash-ga-260731
IMAGE_MODEL=doubao-seedream-5-0-260128
VIDEO_MODEL=doubao-seedance-1-5-pro-251215

# 语音合成（火山引擎语音技术控制台）
VOLC_TTS_APP_ID=你的AppID
VOLC_TTS_ACCESS_TOKEN=你的AccessToken

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
| 项目详情 | `/project/:id` | 全流程可视化 + 预览 |

### 项目详情页功能

- **步骤进度条**：实时显示 6 个步骤的执行状态（等待/进行中/完成/出错）
- **剧本预览**：展开查看每个场景的镜头、对话、情绪
- **角色三视图**：展示每个角色的正面/侧面/背面参考图
- **分镜画面**：网格展示所有生成的场景画面
- **语音播放**：逐镜头播放对话和旁白音频
- **视频预览**：在线播放最终合成的漫剧视频 + 下载

## API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | POST | 创建项目 |
| `/api/projects` | GET | 项目列表 |
| `/api/projects/{id}` | GET | 项目详情（含图片/音频路径） |
| `/api/projects/{id}/generate-all` | POST | 一键生成全流程 |
| `/api/projects/{id}/generate-script` | POST | 生成剧本 |
| `/api/projects/{id}/generate-characters` | POST | 生成角色三视图 |
| `/api/projects/{id}/generate-shots` | POST | 生成分镜画面 |
| `/api/projects/{id}/generate-audio` | POST | 生成语音 |
| `/api/projects/{id}/generate-videos` | POST | 生成 AI 视频 |
| `/api/projects/{id}/compose` | POST | 合成最终视频 |
| `/api/projects/{id}/result` | GET | 获取最终视频路径 |

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
│   │   ├── character_engine.py   # 角色三视图（Seedream 生图）
│   │   ├── shot_engine.py        # 分镜画面生成
│   │   ├── audio_engine.py       # 语音合成（Doubao TTS WebSocket）
│   │   ├── video_engine.py       # AI视频生成（Seedance）
│   │   └── compose_engine.py     # 最终视频合成（FFmpeg）
│   └── utils/
│       ├── prompts.py            # LLM Prompt 模板
│       └── file_utils.py         # 文件工具
├── frontend/                     # 前端（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/index.js          # API 请求封装
│   │   ├── router.js             # 路由配置
│   │   ├── pages/
│   │   │   ├── Home.vue          # 项目列表页
│   │   │   ├── Create.vue        # 创建项目页
│   │   │   └── Project.vue       # 项目详情（全流程可视化）
│   │   ├── App.vue               # 根组件
│   │   ├── main.js               # 入口
│   │   └── style.css             # 全局样式
│   ├── vite.config.js            # Vite 配置（含 API 代理）
│   └── package.json
├── projects/                     # 项目数据（自动生成）
├── requirements.txt
├── .env                          # API Key 配置
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

## 成本估算

| 环节 | 单价 | 单集(5分钟) |
|------|------|------------|
| 剧本改写 (DeepSeek) | ~¥0.01/1K tokens | ~¥0.5 |
| 生图 (Seedream) | ~¥0.04/张 | ~¥2 |
| AI视频 (Seedance) | ~¥0.5/段(5秒) | ~¥25 |
| 语音合成 (TTS) | ~¥5/万字符 | ~¥1 |
| **合计** | | **~¥28/集** |

## 常见问题

**Q: FFmpeg 找不到？**
A: 确保 FFmpeg 已安装并加入系统 PATH。

**Q: 生图/视频 API 报错？**
A: 检查火山引擎账户余额是否充足，Seedance 需要账户余额 >200 元或购买资源包。

**Q: 语音合成 403 错误？**
A: 确认 `VOLC_TTS_APP_ID` 和 `VOLC_TTS_ACCESS_TOKEN` 正确，且已开通语音合成大模型服务（试用版为 `seed-tts-1.0`）。

**Q: 前端页面空白？**
A: 确保后端已启动（端口 8000），Vite 会自动代理 API 请求。

## License

MIT
