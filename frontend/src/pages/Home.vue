<template>
  <div class="home fade-in">
    <!-- 顶部 -->
    <div class="header">
      <div>
        <h1>项目</h1>
        <p class="text-dim text-sm" style="margin-top:4px">管理你的漫剧创作项目</p>
      </div>
      <router-link to="/create" class="btn btn-primary">新建项目</router-link>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && projects.length === 0" class="empty-state">
      <div class="empty-icon">📖</div>
      <h3>还没有项目</h3>
      <p class="text-dim">粘贴一段小说文本，AI 会自动改写剧本、生成画面和配音</p>
      <router-link to="/create" class="btn btn-primary mt-2">创建第一个项目</router-link>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center text-dim" style="padding:60px 0">加载中...</div>

    <!-- 项目列表 -->
    <div v-if="projects.length" class="project-list">
      <div v-for="p in projects" :key="p.id" class="project-row">
        <router-link :to="`/project/${p.id}`" class="project-main">
          <div class="project-name">{{ p.name }}</div>
          <div class="project-meta">
            <span class="text-xs text-dim">{{ p.id }}</span>
            <span :class="['status-badge', statusClass(p.status)]">
              {{ statusText(p.status) }}
            </span>
          </div>
        </router-link>
        <button class="btn-del" @click.stop="del(p.id, p.name)" title="删除项目">删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getProjects, deleteProject } from '../api'

const projects = ref([])
const loading = ref(true)

const load = async () => {
  try {
    const { data } = await getProjects()
    projects.value = data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const del = async (id, name) => {
  if (!confirm(`确定删除「${name}」？此操作不可恢复。`)) return
  try {
    await deleteProject(id)
    await load()
  } catch (e) {
    alert('删除失败')
  }
}

const statusMap = {
  created: '待生成',
  script_generating: '生成剧本',
  script_done: '剧本完成',
  characters_generating: '生成角色',
  characters_done: '角色完成',
  shots_generating: '生成画面',
  shots_done: '画面完成',
  audio_generating: '生成语音',
  audio_done: '语音完成',
  video_generating: '生成视频',
  video_done: '视频完成',
  composing: '合成中',
  done: '已完成',
  error: '出错',
}

const statusText = (s) => statusMap[s] || s
const statusClass = (s) => {
  if (s === 'done') return 'status-done'
  if (s === 'error') return 'status-error'
  if (s.includes('generating') || s === 'composing') return 'status-generating'
  return 'status-created'
}
</script>

<style scoped>
.empty-state {
  text-align: center;
  padding: 80px 20px;
}
.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}
.empty-state h3 {
  font-family: var(--font-display);
  font-size: 18px;
  margin-bottom: 8px;
}
.empty-state p {
  max-width: 320px;
  margin: 0 auto;
  line-height: 1.6;
}

.project-list {
  display: flex;
  flex-direction: column;
}

.project-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border);
}
.project-row:last-child { border-bottom: none; }

.project-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 4px;
  text-decoration: none !important;
  color: var(--text) !important;
  transition: background 0.1s;
}
.project-main:hover { background: var(--bg-hover); }

.project-name {
  font-weight: 500;
  font-size: 15px;
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-del {
  background: none;
  border: none;
  color: var(--text-light);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius);
  transition: all 0.15s;
}
.btn-del:hover {
  color: var(--error);
  background: var(--error-bg);
}
</style>
