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
        <button v-if="project.script && !running" class="btn btn-outline" @click="openAiAssistant">✎ AI 改剧本</button>
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

    <!-- 成本预算横幅 -->
    <div v-if="project.daily_budget" class="budget-bar" :class="{ warn: budgetWarn }">
      <div class="budget-info">
        <span class="budget-dot" aria-hidden="true"></span>
        <span class="budget-label">今日成本</span>
        <span class="budget-num">¥{{ project.spend || 0 }}</span>
        <span class="budget-sep">/ 限额 ¥{{ project.daily_budget }}</span>
      </div>
      <div class="budget-track">
        <div class="budget-fill" :style="{ width: budgetPct + '%' }"></div>
      </div>
      <span v-if="budgetWarn" class="budget-hint">接近限额，AI 视频将自动降级为图文卡点模式</span>
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
            <div class="shot-tools">
              <button v-if="src && !running" class="redo-badge" @click.stop="handleRedoShot(i)" title="重新生成此镜（画质/内容不满意）">↻ 重做此镜</button>
              <button v-if="src" class="delete-badge" @click.stop="handleDeleteSingleShot(i)" title="删除">✕</button>
            </div>
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

    <!-- AI 剧本助手 抽屉 -->
    <Teleport to="body">
      <div v-if="aiOpen" class="ai-mask" @click.self="aiOpen = false"></div>
      <aside v-if="aiOpen" class="ai-drawer" aria-label="AI 剧本助手">
        <div class="ai-head">
          <div>
            <h2>AI 改剧本</h2>
            <p class="ai-sub">按约束修改，超长镜头会被自动拦截重写</p>
          </div>
          <button class="ai-close" @click="aiOpen = false" aria-label="关闭">✕</button>
        </div>

        <div class="ai-body">
          <!-- 历史对话（持久化，关闭再打开不丢失） -->
          <div v-if="aiHistory.length" class="ai-history">
            <div class="ai-history-hd">
              <span>历史对话</span>
              <button class="ai-history-clear" @click="clearAiHistory">清空</button>
            </div>
            <div
              v-for="(m, i) in aiHistory"
              :key="i"
              :class="['ai-hist-item', 'ai-hist-' + m.role]"
            >
              <span class="ai-hist-role">{{ m.role === 'user' ? '我' : (m.role === 'system' ? '系统' : 'AI') }}</span>
              <span class="ai-hist-text">{{ m.text }}</span>
            </div>
          </div>

          <!-- 建议输入 -->
          <div class="ai-chips">
            <button
              v-for="p in aiPresets"
              :key="p"
              class="ai-chip"
              @click="aiInput = p"
            >{{ p }}</button>
          </div>
          <textarea
            v-model="aiInput"
            class="ai-input"
            rows="2"
            placeholder="例如：把镜头 2 那段过长的旁白拆短，控制每镜 45 字以内"
          ></textarea>

          <div class="ai-actions">
            <button
              class="btn btn-primary btn-sm"
              :disabled="aiBusy || !aiInput.trim()"
              @click="handleAiChat"
            >{{ aiBusy ? '改写中…' : '生成修改建议' }}</button>
            <button
              v-if="aiResult"
              class="btn btn-sm"
              :class="aiDirty ? 'btn-primary' : 'btn-outline'"
              :disabled="aiBusy"
              @click="handleAiApply"
            >{{ aiDirty ? '应用此版本' : '已应用' }}</button>
          </div>

          <!-- 对话/建议结果 -->
          <div v-if="aiMsg" :class="['ai-note', aiMsgType]">{{ aiMsg }}</div>

          <template v-if="aiResult">
            <div class="ai-summary">
              <span>镜头数</span>
              <strong>{{ aiResult.before.shots }} → {{ aiResult.after.shots }}</strong>
              <span>总朗读</span>
              <strong>{{ aiResult.before.total_chars }} → {{ aiResult.after.total_chars }} 字</strong>
            </div>

            <!-- 变更镜次逐镜诊断 -->
            <div class="ai-diffs">
              <div class="ai-diff-hd">修改后超长镜头（≤9.5s 达标）</div>
              <template v-if="aiIssues.length">
                <div v-for="s in aiIssues" :key="`${s.scene}-${s.shot}`" class="ai-diff-row over">
                  <span class="ai-diff-idx">S{{ s.scene }}·镜{{ s.shot }}</span>
                  <span class="ai-diff-sec">{{ s.chars }} 字 ≈ {{ s.seconds }}s</span>
                  <span class="ai-tag warn">超限</span>
                </div>
              </template>
              <div v-else class="ai-clear">✓ 无超长镜头，全部在视频可覆盖时长内</div>
            </div>
          </template>

          <!-- 剧本已生效：手动选择要重跑的下游步骤 -->
          <div v-if="!aiDirty && aiResult" class="ai-rerun">
            <div class="ai-rerun-hd">剧本已生效 ✅ 手动选择要重跑的下游步骤</div>
            <p class="ai-rerun-sub">旧分镜/语音/视频仍保留。AI 若只改了台词文本，可只重跑「语音合成」与「AI 视频」；若镜头数/画面描述有变，建议重跑「分镜画面」后依序重跑。</p>
            <div class="ai-rerun-btns">
              <button
                v-for="s in steps"
                :key="s.key"
                v-show="resetStepApi[s.key]"
                class="btn btn-outline btn-sm"
                :disabled="running"
                @click="rerunStep(s.key)"
              >重跑「{{ s.label }}」</button>
            </div>
            <button class="btn btn-ghost btn-sm ai-rerun-later" @click="aiOpen = false">暂时不重跑</button>
          </div>
        </div>
      </aside>
    </Teleport>
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
  updateProjectSettings, redoSingleShot, aiChatScript, applyScript
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
let sseSource = null

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
  } catch (e) { console.error(e) }
}

// 拉取最终视频。仅在项目已完成时调用，避免未合成完成时反复 404 刷后端日志
// 加时间戳参数强制重新加载，确保重做后视频内容更新
const loadFinalVideo = async () => {
  try {
    const { data: r } = await getResult(route.params.id)
    const path = r.video_path
    const base = img(path)
    finalVideoUrl.value = base.includes('?') ? base : `${base}?v=${Date.now()}`
    return true
  } catch (e) {
    return false
  }
}

// ---- AI 剧本助手（保留历史对话）----
const aiOpen = ref(false)
const aiInput = ref('')
const aiBusy = ref(false)
const aiResult = ref(null)      // {before,after,revised,warnings,changed_shots}
const aiDirty = ref(true)       // 建议尚未应用
const aiMsg = ref('')
const aiMsgType = ref('ok')     // ok / warn / err
const aiHistory = ref([])       // [{role:'user'|'assistant'|'system', text, ts}]
const aiPresets = [
  '把所有超过 9.5s 的镜头拆分或精简到 45 字以内',
  '把旁白整体写得简洁一些，控制每镜时长',
  '给台词较多的一镜加上动作描述，并精简对白',
]

const aiHistoryKey = () => `ai_hist_${route.params.id}`
const loadAiHistory = () => {
  try {
    const raw = localStorage.getItem(aiHistoryKey())
    aiHistory.value = raw ? JSON.parse(raw) : []
  } catch (e) { aiHistory.value = [] }
}
const saveAiHistory = () => {
  try { localStorage.setItem(aiHistoryKey(), JSON.stringify(aiHistory.value.slice(-50))) } catch (e) {}
}
const pushAiMsg = (role, text) => {
  if (!text) return
  aiHistory.value.push({ role, text, ts: Date.now() })
  if (aiHistory.value.length > 50) aiHistory.value = aiHistory.value.slice(-50)
  saveAiHistory()
}
const clearAiHistory = () => {
  aiHistory.value = []
  try { localStorage.removeItem(aiHistoryKey()) } catch (e) {}
}

const openAiAssistant = () => {
  aiOpen.value = true
  loadAiHistory()
}

const aiIssues = computed(() => {
  if (!aiResult.value || !aiResult.value.revised) return []
  const shots = []
  const walk = (scenes) => {
    for (const sc of scenes || []) {
      for (const s of sc.shots || []) {
        const chars = (s.narrator || '').length +
          (s.dialogues || []).reduce((n, d) => n + (d.line || '').length, 0)
        const secs = chars / 5
        shots.push({ scene: sc.scene_number, shot: s.shot_number, chars, seconds: Number(secs.toFixed(1)) })
      }
    }
  }
  walk(aiResult.value.revised.scenes)
  return shots.filter(x => x.seconds > 9.5)
})

const handleAiChat = async () => {
  if (!aiInput.value.trim()) return
  const instruction = aiInput.value.trim()
  const historySnapshot = aiHistory.value.map(m => ({ role: m.role, text: m.text }))
  aiBusy.value = true
  aiMsg.value = ''
  aiMsgType.value = 'ok'
  aiResult.value = null
  try {
    const { data } = await aiChatScript(route.params.id, instruction, false, historySnapshot)
    if (data.code === 'budget_confirm') {
      const go = window.confirm(`${data.message}\n\n继续将消耗少量 token 用于 AI 改写。`)
      if (!go) { aiBusy.value = false; return }
      const { data: forced } = await aiChatScript(route.params.id, instruction, true, historySnapshot)
      data.code = undefined
      Object.assign(data, forced)
    }
    aiResult.value = data
    aiDirty.value = true
    aiMsg.value = '已生成修改建议，请核对下方时长诊断后点击「应用此版本」。'
    aiMsgType.value = 'ok'
    pushAiMsg('user', instruction)
    pushAiMsg('assistant', `生成修改建议：镜头 ${data.before?.shots ?? '?'} → ${data.after?.shots ?? '?'}，总朗读 ${data.before?.total_chars ?? '?'} → ${data.after?.total_chars ?? '?'} 字`)
    aiInput.value = ''
  } catch (e) {
    aiMsg.value = '改写失败：' + (e.response?.data?.detail || e.message)
    aiMsgType.value = 'err'
    pushAiMsg('system', '改写失败：' + (e.response?.data?.detail || e.message))
  } finally {
    aiBusy.value = false
  }
}

const handleAiApply = async () => {
  if (!aiResult.value || !aiDirty.value) return
  const n = aiResult.value.revised
  const beforeCount = aiResult.value.before?.shots ?? 0
  const afterCount = aiResult.value.after?.shots ?? 0
  const msg = beforeCount === afterCount
    ? '应用后将替换剧本；旧分镜/语音/视频仍保留。若镜头内容有变，请删除对应资产后重跑以同步。是否继续？'
    : `应用后将替换剧本（镜头数 ${beforeCount} → ${afterCount}）。镜头数有变，旧分镜/语音/视频序号不再匹配，请删除后重新生成。是否继续？`
  if (!window.confirm(msg)) return
  aiBusy.value = true
  try {
    await applyScript(route.params.id, n)
    aiDirty.value = false
    aiMsg.value = '已应用（已备份旧剧本）。旧分镜/语音/视频仍保留供参考；需要同步时，删除对应资产后点击步骤重跑即可。'
    aiMsgType.value = 'ok'
    pushAiMsg('system', `已应用修改：镜头 ${beforeCount} → ${afterCount}`)
    await loadProject()
  } catch (e) {
    aiMsg.value = '应用失败：' + (e.response?.data?.detail || e.message)
    aiMsgType.value = 'err'
  } finally {
    aiBusy.value = false
  }
}

// ---- 成本预算 ----
const budgetPct = computed(() => {
  const b = project.value.daily_budget
  if (!b) return 0
  return Math.min(100, Math.round(((project.value.spend || 0) / b) * 100))
})
const budgetWarn = computed(() => budgetPct.value >= 80)

const handleRedoShot = async (index) => {
  if (!confirm(`重新生成镜头 ${index + 1}？将重做该镜的画面/音频/视频并重新合成，其余镜头保留。`)) return
  running.value = true
  try {
    const started = await runWithBudget((force) => redoSingleShot(route.params.id, index, force), '单镜重做')
    if (!started) { running.value = false; return }
    startPolling()
  } catch (e) {
    alert('重做失败: ' + (e.response?.data?.detail || e.message))
    running.value = false
  }
}

// ---- SSE 实时订阅（节流刷新 + 断线重连）----
let sseRetryTimer = null
let sseRetryCount = 0
let lastProjectRefresh = 0
let pendingProjectRefresh = null

const refreshProjectThrottled = () => {
  const now = Date.now()
  // 距上次刷新不足 1.5s 时合并到下一次再刷，避免每个 log 都全量拉取
  if (pendingProjectRefresh) return
  const wait = Math.max(0, 1500 - (now - lastProjectRefresh))
  const doRefresh = async () => {
    pendingProjectRefresh = null
    lastProjectRefresh = Date.now()
    await loadProject()
    // 合成完成 → 顺带刷新最终视频
    if (project.value.status === 'done' && !finalVideoUrl.value) {
      await loadFinalVideo()
    }
  }
  pendingProjectRefresh = setTimeout(doRefresh, wait)
}

const connectSse = () => {
  if (sseSource) sseSource.close()
  if (sseRetryTimer) { clearTimeout(sseRetryTimer); sseRetryTimer = null }
  if (!window.EventSource) return
  const es = new EventSource(`/api/projects/${route.params.id}/events`)
  es.addEventListener('open', () => { sseRetryCount = 0 })
  es.addEventListener('log', async (ev) => {
    try {
      const log = JSON.parse(ev.data)
      // 日志面板增量刷新（轻量）
      await loadLogs()
      const msg = log.message || ''
      // 完成类日志 → 节流刷新项目（画面/语音/视频出片即时可见）
      if (msg.includes('画面完成') || msg.includes('语音完成') || msg.includes('视频完成') ||
          (msg.includes('分镜') && msg.includes('完成')) || msg.includes('重做')) {
        refreshProjectThrottled()
      }
    } catch (e) {}
  })
  es.addEventListener('error', () => {
    // 浏览器触发重连失败时手动退避重连
    if (es.readyState === EventSource.CLOSED && !sseSource) return
    if (sseRetryCount >= 10) return // 上限 10 次，避免后台空转
    sseRetryCount += 1
    const delay = Math.min(15000, 1000 * 2 ** sseRetryCount)
    sseRetryTimer = setTimeout(() => {
      if (running.value) connectSse()
    }, delay)
  })
  sseSource = es
}

const stepApi = {
  script: generateScript,
  characters: generateCharacters,
  shots: generateShots,
  audio: generateAudio,
  video: generateVideos,
  compose: composeVideo,
}

// 预算确认：若接口返回 budget_confirm（今日花费将超限额），弹窗询问是否继续。
// fn(force) 为执行函数：先 fn(false) 试探，确认继续后用 fn(true) 真正执行。
const runWithBudget = async (fn, label) => {
  const resp = await fn(false)
  const data = resp?.data || {}
  if (data.code === 'budget_confirm') {
    const go = window.confirm(
      `${data.message}\n\n点击「确定」将超出限额继续生成，费用会照常累计；点击「取消」则停止本次操作。`
    )
    if (!go) return false
    await fn(true)  // force=true 继续
  }
  return true
}

// 重跑某步：弹窗让用户选择「增量补全」或「清空重建」
const resetStepApi = {
  characters: deleteCharacters,
  shots: deleteShots,
  audio: deleteAudio,
  videos: deleteVideos,
  compose: deleteOutput,
}

const chooseRerunMode = (label) => {
  const rebuild = window.confirm(
    `重跑「${label}」\n\n【确定】= 清空重建：删除该步骤旧产物，全部重做\n【取消】= 增量补全：已存在的跳过，仅补缺失`
  )
  if (rebuild) return 'rebuild'
  const incremental = window.confirm(`「${label}」将执行「增量补全」：不删除已存在产物，仅生成缺失部分。\n\n确认继续？`)
  return incremental ? 'incremental' : null
}

const doRunStep = async (key, mode = 'incremental') => {
  if (running.value) {
    alert('当前有任务正在运行，请先停止或等待完成')
    return false
  }
  running.value = true
  try {
    const reset = resetStepApi[key]
    if (mode === 'rebuild' && reset) {
      try { await reset(route.params.id) } catch (e) {}
    }
    const apiFn = stepApi[key]
    const started = await runWithBudget((force) => apiFn(route.params.id, force), steps.value.find(s => s.key === key)?.label || key)
    if (!started) { running.value = false; return false }
    await loadProject()
    startPolling()
    return true
  } catch (e) {
    alert('失败: ' + (e.response?.data?.detail || e.message))
    running.value = false
    return false
  }
}

const rerunStep = async (key) => {
  if (running.value) {
    alert('当前有任务正在运行，请先停止或等待完成')
    return
  }
  const label = steps.value.find(s => s.key === key)?.label
  const mode = chooseRerunMode(label)
  if (!mode) return
  await doRunStep(key, mode)
}

const startFull = async () => {
  running.value = true
  try {
    const started = await runWithBudget((force) => generateAll(route.params.id, force), '一键全流程')
    if (!started) { running.value = false; return }
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
    if (sseSource) { sseSource.close(); sseSource = null }
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
        await loadFinalVideo()
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
  loadAiHistory()
  // 已完成项目：初始即拉取最终视频
  if (project.value.status === 'done') {
    await loadFinalVideo()
  }
  connectSse()
  const s = project.value.status
  const isRunning = s && (s.includes('generating') || s === 'composing')
  if (isRunning) {
    running.value = true
    startPolling()
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (logTimer) clearInterval(logTimer)
  if (sseRetryTimer) clearTimeout(sseRetryTimer)
  if (pendingProjectRefresh) clearTimeout(pendingProjectRefresh)
  if (sseSource) { sseSource.close(); sseSource = null }
})
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

/* 成本预算横幅 */
.budget-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 20px;
  font-size: 12px;
  flex-wrap: wrap;
}
.budget-bar.warn { border-color: #FDE68A; background: var(--warning-bg); }
.budget-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-bg);
}
.budget-bar.warn .budget-dot { background: var(--warning); box-shadow: 0 0 0 3px #FEF3C7; }
.budget-info { display: flex; align-items: baseline; gap: 6px; }
.budget-label { color: var(--text-dim); }
.budget-num { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.budget-sep { color: var(--text-light); }
.budget-track {
  flex: 1; min-width: 120px; height: 5px;
  background: var(--bg-hover);
  border-radius: 100px; overflow: hidden;
}
.budget-fill { height: 100%; background: var(--primary-light); border-radius: 100px; transition: width .3s ease; }
.budget-bar.warn .budget-fill { background: var(--warning); }
.budget-hint { color: var(--warning); font-weight: 500; }

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
  background: var(--bg-hover);
}
.shot-card > div:first-child { height: 100%; }
.shot-card:hover { opacity: 0.92; }
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
  pointer-events: none;
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

/* 卡片悬浮工具（重做 / 删除） */
.shot-tools {
  position: absolute;
  top: 4px;
  left: 4px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.shot-card:hover .shot-tools { opacity: 1; }
.redo-badge {
  height: 22px;
  padding: 0 8px;
  border: none;
  border-radius: 100px;
  background: rgba(0,0,0,0.7);
  color: white;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.redo-badge:hover { background: var(--primary); }

.delete-badge {
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
.shot-card:hover .delete-badge { position: static; }
.delete-badge:hover { background: var(--error); }

/* 视频卡片的删除仍悬浮右上 */
.video-card .delete-badge { position: absolute; top: 4px; right: 4px; }
.shot-tools .delete-badge { position: static; }

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

<style>
/* AI 剧本助手抽屉（Teleport 到 body，需非 scoped） */
.ai-mask {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, 0.4);
  z-index: 1100;
  animation: fadeIn 0.2s ease;
}
.ai-drawer {
  position: fixed;
  top: 0;
  right: 0;
  height: 100vh;
  width: min(420px, 92vw);
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  z-index: 1101;
  display: flex;
  flex-direction: column;
  animation: fadeIn 0.2s ease;
}
.ai-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
}
.ai-head h2 {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}
.ai-sub {
  font-size: 12px;
  color: var(--text-light);
  margin: 2px 0 0;
}
.ai-close {
  border: none;
  background: var(--bg-hover);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-dim);
  font-size: 13px;
}
.ai-close:hover { background: var(--border); color: var(--text); }

.ai-body {
  padding: 16px 20px 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-history {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  padding: 8px 10px;
  max-height: 240px;
  overflow-y: auto;
}
.ai-history-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.ai-history-clear {
  background: none;
  border: none;
  color: var(--text-light);
  font-size: 11px;
  cursor: pointer;
}
.ai-history-clear:hover { color: var(--error); }
.ai-hist-item {
  display: flex;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
  padding: 4px 0;
  border-bottom: 1px dashed var(--border);
}
.ai-hist-item:last-child { border-bottom: none; }
.ai-hist-role { flex-shrink: 0; font-weight: 600; }
.ai-hist-user .ai-hist-role { color: var(--primary); }
.ai-hist-assistant .ai-hist-role { color: var(--success); }
.ai-hist-system .ai-hist-role { color: var(--warning); }
.ai-hist-text { color: var(--text-dim); word-break: break-word; }
.ai-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ai-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 100px;
  border: 1px solid var(--border-dark);
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.ai-chip:hover { border-color: var(--primary); color: var(--primary); background: var(--primary-bg); }

.ai-input {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
  font-family: var(--font-body);
  resize: vertical;
}
.ai-input:focus { outline: none; border-color: var(--primary); }

.ai-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.ai-note {
  font-size: 13px;
  padding: 10px 12px;
  border-radius: var(--radius);
  line-height: 1.5;
}
.ai-note.ok { background: var(--success-bg); color: var(--success); }
.ai-note.warn { background: var(--warning-bg); color: var(--warning); }
.ai-note.err { background: var(--error-bg); color: var(--error); }

.ai-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--text-dim);
  padding: 10px 12px;
  background: var(--bg-hover);
  border-radius: var(--radius);
  flex-wrap: wrap;
}
.ai-summary strong { color: var(--text); font-size: 13px; font-variant-numeric: tabular-nums; }

.ai-diffs { border-top: 1px dashed var(--border-dark); padding-top: 12px; }
.ai-diff-hd {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.ai-diff-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}
.ai-diff-row:last-child { border-bottom: none; }
.ai-diff-idx {
  min-width: 84px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
  font-weight: 500;
}
.ai-diff-sec { color: var(--text-dim); flex: 1; font-variant-numeric: tabular-nums; }
.ai-diff-row.over .ai-diff-idx { color: var(--error); }

.ai-tag {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 100px;
}
.ai-tag.warn { background: var(--error-bg); color: var(--error); }
.ai-clear { color: var(--success); font-size: 13px; }

/* 剧本已生效后：手动选择重跑 */
.ai-rerun {
  border-top: 1px solid var(--border);
  margin-top: 8px;
  padding-top: 14px;
}
.ai-rerun-hd {
  font-size: 14px;
  font-weight: 700;
  color: var(--success);
  margin-bottom: 6px;
}
.ai-rerun-sub {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin-bottom: 10px;
}
.ai-rerun-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.ai-rerun-btns .btn { margin: 0; }
.ai-rerun-later { color: var(--text-light); margin-top: 8px; }
</style>
