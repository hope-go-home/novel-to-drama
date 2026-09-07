<template>
  <div class="project-page fade-in">
    <!-- 顶栏 -->
    <div class="header">
      <div>
        <h1>{{ project.name || '...' }}</h1>
        <p class="text-xs text-dim" style="margin-top:2px">{{ $route.params.id }}</p>
      </div>
      <div class="header-actions">
        <div class="tts-seg" title="声音方案：配音=角色TTS对白+旁白并丢视频原声；原声=保留AI视频自带声音拼接">
          <button class="btn btn-xs" :class="project.use_tts !== false ? 'btn-primary' : 'btn-ghost'" :disabled="running" @click="handleToggleTts(true)">TTS 配音</button>
          <button class="btn btn-xs" :class="project.use_tts === false ? 'btn-primary' : 'btn-ghost'" :disabled="running" @click="handleToggleTts(false)">AI 原声</button>
        </div>
        <button v-if="!running" class="btn btn-primary" @click="startFull">一键生成</button>
        <button v-if="running" class="btn btn-outline" @click="handleStop" style="color:var(--error);border-color:var(--error)">停止</button>
        <router-link to="/" class="btn btn-outline btn-sm">返回</router-link>
      </div>
    </div>

    <!-- 流水线进度 -->
    <div class="pipeline">
      <div
        v-for="(step, i) in steps"
        :key="step.key"
        :class="['pipe-step', stepStatus(step.key)]"
        @click="rerunStep(step.key)"
        :title="'点击重跑: ' + step.label"
      >
        <div class="pipe-num">{{ i + 1 }}</div>
        <div class="pipe-info">
          <div class="pipe-label">{{ step.label }}</div>
          <div class="pipe-status">{{ stepStatusText(step.key) }}</div>
        </div>
        <div v-if="i < steps.length - 1" class="pipe-arrow">→</div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="project.error_message" class="error-banner">
      <strong>出错</strong>
      <span>{{ project.error_message }}</span>
    </div>

    <!-- 日志面板 -->
    <LogPanel :logs="logs" @clear="handleClearLogs" @refresh="loadLogs" class="mb-3" />

    <!-- 内容区 -->
    <div class="sections">

      <!-- 剧本 -->
      <section v-if="project.script" class="section">
        <div class="section-header">
          <h2 class="section-title">剧本</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteScript">删除剧本</button>
        </div>

        <div class="script-meta">
          <div class="meta-item">
            <span class="meta-label">标题</span>
            <span class="meta-value">{{ project.script.title }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">角色</span>
            <span class="meta-value">
              <span v-for="c in project.script.characters" :key="c.name" class="tag">{{ c.name }}</span>
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">场景</span>
            <span class="meta-value">{{ project.script.scenes?.length || 0 }} 个</span>
          </div>
        </div>

        <div class="scene-list">
          <div v-for="scene in project.script.scenes" :key="scene.scene_number" class="scene">
            <div class="scene-head" @click="toggleScene(scene.scene_number)">
              <span class="scene-name">场景 {{ scene.scene_number }} · {{ scene.location }}</span>
              <span class="scene-meta">{{ scene.mood }} · {{ scene.shots?.length }} 镜头</span>
            </div>
            <div v-if="expandedScenes[scene.scene_number]" class="scene-body">
              <div v-for="shot in scene.shots" :key="shot.shot_number" class="shot">
                <span class="shot-num">{{ shot.shot_number }}</span>
                <div class="shot-content">
                  <div class="shot-desc">
                    <span class="shot-type">{{ shot.shot_type }}</span>
                    {{ shot.description }}
                  </div>
                  <!-- 适配 dialogues 数组 -->
                  <template v-if="shot.dialogues?.length">
                    <div v-for="(d, di) in shot.dialogues" :key="di" class="shot-dialogue">
                      <span class="dialogue-char">{{ d.character }}</span>
                      <span class="dialogue-line">「{{ d.line }}」</span>
                      <span class="dialogue-emotion">{{ d.emotion }}</span>
                    </div>
                  </template>
                  <div v-if="shot.narrator" class="shot-narrator">
                    <span class="narrator-label">旁白</span> {{ shot.narrator }}
                  </div>
                  <div v-if="shot.duration" class="shot-duration">
                    <span class="duration-label">时长</span> {{ shot.duration }}s
                  </div>
                  <div v-if="shot.sound_effects?.length" class="shot-sfx">
                    <span class="sfx-label">音效</span>
                    <span v-for="(s, si) in shot.sound_effects" :key="si" class="sfx-item">{{ s.name }}({{ s.start }}–{{ s.end }}s, {{ s.vol }})</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 角色 -->
      <section v-if="project.characters?.length" class="section">
        <div class="section-header">
          <h2 class="section-title">角色设计</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteCharacters">删除角色</button>
        </div>
        <div class="char-grid">
          <div v-for="char in project.characters" :key="char.character_name" class="char-card">
            <div class="char-info">
              <h4>{{ char.character_name }}</h4>
              <p class="text-sm text-dim">{{ char.description }}</p>
            </div>
            <div class="char-views">
              <div v-if="char.front_image" class="view" @click="lightbox = img(char.front_image)">
                <img :src="img(char.front_image)" alt="正面" />
                <span>正面</span>
              </div>
              <div v-if="char.side_image" class="view" @click="lightbox = img(char.side_image)">
                <img :src="img(char.side_image)" alt="侧面" />
                <span>侧面</span>
              </div>
              <div v-if="char.back_image" class="view" @click="lightbox = img(char.back_image)">
                <img :src="img(char.back_image)" alt="背面" />
                <span>背面</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 分镜画面 -->
      <section v-if="shotImages.length" class="section">
        <div class="section-header">
          <h2 class="section-title">分镜画面</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteShots">全部删除</button>
        </div>
        <div class="shot-grid">
          <div v-for="(src, i) in shotImages" :key="i" class="shot-card">
            <div v-if="src" @click="lightbox = img(src)">
                <img :src="img(src)" :alt="'镜头 ' + (i+1)" />
              <div class="shot-label">{{ i + 1 }}</div>
            </div>
            <div v-else class="shot-empty">
              <span>{{ i + 1 }}</span>
              <span class="text-xs">无画面</span>
            </div>
            <button v-if="src" class="delete-badge" @click.stop="handleDeleteSingleShot(i)" title="删除">✕</button>
          </div>
        </div>
      </section>

      <!-- 图片放大弹窗 -->
      <div v-if="lightbox" class="lightbox" @click="lightbox = null">
        <img :src="lightbox" />
      </div>

      <!-- 语音 -->
      <section v-if="audioPaths.length" class="section">
        <div class="section-header">
          <h2 class="section-title">语音</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteAudio">全部删除</button>
        </div>
        <div class="audio-list">
          <template v-for="(a, i) in audioPaths" :key="i">
            <div v-if="a.dialogue_audio || a.narrator_audio" class="audio-row">
              <span class="audio-idx">{{ i + 1 }}</span>
              <div class="audio-players">
                <div v-if="a.dialogue_audio" class="audio-item">
                  <span class="audio-label">对话</span>
                  <audio controls :src="img(a.dialogue_audio)" />
                </div>
                <div v-if="a.narrator_audio" class="audio-item">
                  <span class="audio-label">旁白</span>
                  <audio controls :src="img(a.narrator_audio)" />
                </div>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- AI 视频片段 -->
      <section v-if="videoPaths.length" class="section">
        <div class="section-header">
          <h2 class="section-title">AI 视频片段</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteVideos">全部删除</button>
        </div>
        <div class="video-grid">
          <div v-for="(src, i) in videoPaths" :key="i" class="video-card">
            <div v-if="src" class="video-wrap">
              <video controls :src="img(src)" preload="metadata" />
              <div class="video-label">{{ i + 1 }}</div>
            </div>
            <div v-else class="video-empty">
              <span>{{ i + 1 }}</span>
              <span class="text-xs">无视频</span>
            </div>
            <button v-if="src" class="delete-badge" @click="handleDeleteSingleVideo(i)" title="删除">✕</button>
          </div>
        </div>
      </section>

      <!-- 最终视频 -->
      <section v-if="finalVideoUrl" class="section">
        <div class="section-header">
          <h2 class="section-title">最终视频</h2>
          <button class="btn btn-danger btn-xs" @click="handleDeleteOutput">删除</button>
        </div>
        <div v-if="finalVideoUrl" class="video-area">
          <video controls :src="finalVideoUrl" />
          <a :href="finalVideoUrl" download class="btn btn-outline mt-2">下载视频</a>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  getProject, generateAll, getResult, stopProject,
  generateScript, generateCharacters, generateShots,
  generateAudio, generateVideos, composeVideo,
  deleteScript, deleteCharacters, deleteShots, deleteAudio,
  deleteVideos, deleteOutput, deleteSingleShot, deleteSingleVideo,
  updateProjectSettings
} from '../api'
import { getLogs, clearLogs } from '../api'
import LogPanel from '../components/LogPanel.vue'

const route = useRoute()
const project = ref({})
const running = ref(false)
const finalVideoUrl = ref('')
const shotImages = ref([])
const audioPaths = ref([])
const videoPaths = ref([])
const expandedScenes = reactive({})
const lightbox = ref(null)
const logs = ref([])
let pollTimer = null
let logTimer = null

const ALL_STEPS = [
  { key: 'script', label: '剧本改写' },
  { key: 'characters', label: '角色设计' },
  { key: 'shots', label: '分镜画面' },
  { key: 'audio', label: '语音合成' },
  { key: 'video', label: 'AI 视频' },
  { key: 'compose', label: '最终合成' },
]
// AI 原声模式（use_tts=false）不生成配音，流程里就不显示"语音合成"
const steps = computed(() => {
  const all = ALL_STEPS
  return project.value.use_tts !== false ? all : all.filter(s => s.key !== 'audio')
})

const stepStatus = (key) => {
  const s = project.value.status || ''
  const prefix = ['script', 'characters', 'shots']
  const suffix = ['video', 'compose', 'done']
  const order = project.value.use_tts !== false
    ? [...prefix, 'audio', ...suffix]
    : [...prefix, ...suffix]
  const cur = order.findIndex(k => s.includes(k))
  const idx = order.indexOf(key)
  if (s === 'done') return idx <= cur ? 'done' : 'pending'
  if (s === 'error') return idx < cur ? 'done' : idx === cur ? 'error' : 'pending'
  if (s.includes(key) && s.includes('generating')) return 'running'
  if (s.includes(key) && s.includes('done')) return 'done'
  if (idx < cur) return 'done'
  return 'pending'
}

const stepStatusText = (key) => {
  const m = { pending: '等待', running: '进行中', done: '完成', error: '出错' }
  return m[stepStatus(key)] || ''
}

const toggleScene = (n) => { expandedScenes[n] = !expandedScenes[n] }

const img = (path) => {
  if (!path) return ''
  const m = path.match(/projects[/\\](.+)/)
  if (m) {
    const parts = m[1].replace(/\\/g, '/').split('/')
    const encoded = parts.map(p => encodeURIComponent(p)).join('/')
    return `/static/projects/${encoded}`
  }
  return path
}

const loadProject = async () => {
  try {
    const { data } = await getProject(route.params.id)
    project.value = data
    shotImages.value = data.shot_images || []
    audioPaths.value = data.audio_paths || []
    videoPaths.value = data.video_paths || []
    // 加载最终视频（只要有 result 文件就显示，不依赖 status）
    try {
      const { data: r } = await getResult(route.params.id)
      finalVideoUrl.value = img(r.video_path)
    } catch (e) {
      finalVideoUrl.value = ''
    }
  } catch (e) { console.error(e) }
}

const stepApi = {
  script: generateScript,
  characters: generateCharacters,
  shots: generateShots,
  audio: generateAudio,
  video: generateVideos,
  compose: composeVideo,
}

const rerunStep = async (key) => {
  if (running.value) {
    alert('当前有任务正在运行，请先停止或等待完成')
    return
  }
  if (!confirm(`重跑「${steps.value.find(s => s.key === key)?.label}」？`)) return
  running.value = true
  try {
    await stepApi[key](route.params.id)
    await loadProject()
    startPolling()
  } catch (e) {
    alert('失败: ' + (e.response?.data?.detail || e.message))
    running.value = false
  }
}

const startFull = async () => {
  running.value = true
  try {
    await generateAll(route.params.id)
    startPolling()
  } catch (e) {
    alert('失败: ' + (e.response?.data?.detail || e.message))
    running.value = false
  }
}

const handleStop = async () => {
  if (!confirm('确定停止当前生成？')) return
  try {
    await stopProject(route.params.id)
    running.value = false
    if (pollTimer) clearInterval(pollTimer)
    if (logTimer) clearInterval(logTimer)
    await loadProject()
    await loadLogs()
  } catch (e) {
    alert('停止失败: ' + (e.response?.data?.detail || e.message))
  }
}

// 删除操作
const handleDeleteScript = async () => {
  if (!confirm('确定删除剧本？这将同时删除分镜、语音、视频')) return
  await deleteScript(route.params.id)
  await loadProject()
}

const handleDeleteCharacters = async () => {
  if (!confirm('确定删除角色设计？')) return
  await deleteCharacters(route.params.id)
  await loadProject()
}

const handleDeleteShots = async () => {
  if (!confirm('确定删除所有分镜画面？')) return
  await deleteShots(route.params.id)
  await loadProject()
}

const handleDeleteAudio = async () => {
  if (!confirm('确定删除所有语音？')) return
  await deleteAudio(route.params.id)
  await loadProject()
}

const handleDeleteVideos = async () => {
  if (!confirm('确定删除所有视频片段？')) return
  await deleteVideos(route.params.id)
  await loadProject()
}

const handleDeleteOutput = async () => {
  if (!confirm('确定删除最终视频？')) return
  await deleteOutput(route.params.id)
  finalVideoUrl.value = ''
  await loadProject()
}

const handleToggleTts = async (val) => {
  if (running.value) {
    alert('请先停止当前任务再切换声音方案')
    return
  }
  const label = val ? 'TTS 配音' : 'AI 原声拼接'
  if (!confirm(`切换到「${label}」？\n提示：切换后需删除已生成的音频/视频并重跑，新方案才生效。`)) return
  try {
    await updateProjectSettings(route.params.id, { use_tts: val })
    await loadProject()
  } catch (e) {
    alert('切换失败: ' + (e.response?.data?.detail || e.message))
  }
}

const handleDeleteSingleShot = async (index) => {
  if (!confirm(`确定删除分镜 ${index + 1}？`)) return
  await deleteSingleShot(route.params.id, index)
  await loadProject()
}

const handleDeleteSingleVideo = async (index) => {
  if (!confirm(`确定删除视频片段 ${index + 1}？`)) return
  await deleteSingleVideo(route.params.id, index)
  await loadProject()
}

const loadLogs = async () => {
  try {
    const { data } = await getLogs(100, route.params.id)
    logs.value = data
  } catch (e) {}
}

const handleClearLogs = async () => {
  try {
    await clearLogs()
    logs.value = []
  } catch (e) {}
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  if (logTimer) clearInterval(logTimer)

  const checkStatus = async () => {
    await loadProject()
    await loadLogs()
    const s = project.value.status
    const isTerminal = s === 'done' || s === 'error' || s === 'created' || s.endsWith('_done')
    if (isTerminal) {
      clearInterval(pollTimer)
      clearInterval(logTimer)
      running.value = false
      if (s === 'done') {
        try {
          const { data } = await getResult(route.params.id)
          finalVideoUrl.value = img(data.video_path)
        } catch (e) {}
      }
    }
  }

  checkStatus()
  pollTimer = setInterval(checkStatus, 3000)
  logTimer = setInterval(loadLogs, 2000)
}

onMounted(async () => {
  await loadProject()
  await loadLogs()
  const s = project.value.status
  const isRunning = s && (s.includes('generating') || s === 'composing')
  if (isRunning) {
    running.value = true
    startPolling()
  }
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; align-items: center; }
.tts-seg { display: inline-flex; gap: 4px; border: 1px solid var(--border); border-radius: var(--radius); padding: 2px; }
.tts-seg .btn { padding: 3px 10px; font-size: 11px; }

/* 流水线 */
.pipeline {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 16px 0;
  margin-bottom: 24px;
  overflow-x: auto;
}

.pipe-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  position: relative;
}
.pipe-step:hover { background: var(--bg-hover); }

.pipe-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  background: var(--border);
  color: var(--text-dim);
}

.pipe-label { font-size: 13px; font-weight: 500; }
.pipe-status { font-size: 11px; color: var(--text-light); }

.pipe-arrow {
  color: var(--border-dark);
  margin: 0 4px;
  font-size: 14px;
  flex-shrink: 0;
}

.pipe-step.done .pipe-num { background: var(--success-bg); color: var(--success); }
.pipe-step.running .pipe-num { background: var(--info-bg); color: var(--info); animation: pulse 1.5s infinite; }
.pipe-step.error .pipe-num { background: var(--error-bg); color: var(--error); }
.pipe-step.pending { opacity: 0.45; }

/* 错误 */
.error-banner {
  background: var(--error-bg);
  border: 1px solid #FECACA;
  color: var(--error);
  padding: 12px 16px;
  border-radius: var(--radius);
  margin-bottom: 20px;
  font-size: 13px;
  display: flex;
  gap: 8px;
}

/* 内容区 */
.sections { display: flex; flex-direction: column; gap: 28px; }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
  margin: 0;
}

.btn-danger {
  background: var(--error-bg);
  color: var(--error);
  border: 1px solid #FECACA;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-danger:hover { background: #FEE2E2; }

.btn-xs { font-size: 11px; padding: 3px 10px; }

/* 剧本 */
.script-meta {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.meta-item { display: flex; gap: 6px; align-items: baseline; }
.meta-label { font-size: 12px; color: var(--text-light); }
.meta-value { font-size: 14px; }

.tag {
  display: inline-block;
  padding: 1px 8px;
  background: var(--bg-hover);
  border-radius: 100px;
  font-size: 12px;
  margin: 0 3px;
}

.scene-list { display: flex; flex-direction: column; }

.scene {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  overflow: hidden;
}

.scene-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
}
.scene-head:hover { background: var(--bg-hover); }

.scene-name { font-size: 14px; font-weight: 500; }
.scene-meta { font-size: 12px; color: var(--text-dim); }

.scene-body { padding: 0 14px 12px; }

.shot {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.shot:last-child { border-bottom: none; }

.shot-num {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-bg);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 1px;
}

.shot-content { flex: 1; }
.shot-type {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
  margin-right: 6px;
}

.shot-dialogue {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-dim);
}
.dialogue-char { font-weight: 600; color: var(--text); }
.dialogue-line { margin: 0 4px; }
.dialogue-emotion { font-style: italic; }

.shot-narrator {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-light);
  font-style: italic;
}
.narrator-label {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  font-style: normal;
}

.shot-duration {
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-dim);
}
.duration-label {
  color: var(--primary);
  font-weight: 600;
  margin-right: 4px;
}

.shot-sfx {
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-dim);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.sfx-label {
  color: var(--warning);
  font-weight: 600;
}
.sfx-item {
  background: var(--bg-hover);
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
}

/* 角色 */
.char-grid { display: flex; flex-direction: column; gap: 16px; }

.char-card {
  display: flex;
  gap: 20px;
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.char-info { flex: 1; min-width: 0; }
.char-info h4 { font-size: 15px; margin-bottom: 6px; }
.char-info p { line-height: 1.5; }

.char-views { display: flex; gap: 8px; flex-shrink: 0; }
.view { text-align: center; cursor: pointer; }
.view:hover { opacity: 0.85; }
.view img {
  width: 100px;
  height: 130px;
  object-fit: cover;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
.view span {
  display: block;
  font-size: 11px;
  color: var(--text-light);
  margin-top: 4px;
}

/* 分镜 */
.shot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.shot-card {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  aspect-ratio: 16/9;
  cursor: pointer;
}
.shot-card:hover { opacity: 0.85; }
.shot-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.shot-label {
  position: absolute;
  bottom: 6px;
  left: 6px;
  background: rgba(0,0,0,0.65);
  color: white;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 100px;
}
.shot-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: var(--bg-hover);
  color: var(--text-light);
}

.delete-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0,0,0,0.7);
  color: white;
  border: none;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.shot-card:hover .delete-badge,
.video-card:hover .delete-badge { opacity: 1; }
.delete-badge:hover { background: var(--error); }

/* 视频片段 */
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.video-card {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
}
.video-wrap {
  position: relative;
}
.video-wrap video {
  width: 100%;
  display: block;
  aspect-ratio: 16/9;
  object-fit: cover;
  background: #000;
}
.video-label {
  position: absolute;
  bottom: 6px;
  left: 6px;
  background: rgba(0,0,0,0.65);
  color: white;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 100px;
}
.video-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 140px;
  background: var(--bg-hover);
  color: var(--text-light);
}

/* 语音 */
.audio-list { display: flex; flex-direction: column; }

.audio-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.audio-row:last-child { border-bottom: none; }

.audio-idx {
  width: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--text-light);
  font-weight: 500;
}

.audio-players { display: flex; gap: 16px; align-items: center; }
.audio-item { display: flex; align-items: center; gap: 6px; }
.audio-label { font-size: 11px; color: var(--text-dim); }
.audio-item audio { height: 30px; }

/* 最终视频 */
.video-area { text-align: center; }
.video-area video {
  max-width: 100%;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
}

/* 图片放大弹窗 */
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}
.lightbox img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: var(--radius);
}
</style>
