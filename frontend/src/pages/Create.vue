<template>
  <div class="create fade-in">
    <div class="header">
      <h1>新建项目</h1>
      <router-link to="/" class="btn btn-ghost btn-sm">返回列表</router-link>
    </div>

    <div class="form-card">
      <div class="form-section">
        <label for="name">项目名称</label>
        <input
          id="name"
          type="text"
          v-model="name"
          placeholder="给你的漫剧起个名字"
        />
      </div>

      <div class="form-section">
        <label for="novel">小说文本</label>
        <textarea
          id="novel"
          v-model="novelText"
          rows="16"
          placeholder="粘贴小说片段到这里...&#10;&#10;建议 3000 字以内，包含对话和场景描写的片段效果更好"
        ></textarea>
        <div class="char-count">
          <span :class="{ 'count-warn': novelText.length > 5000 }">{{ novelText.length.toLocaleString() }}</span>
          <span class="text-dim"> / 5,000 字</span>
        </div>
      </div>

      <!-- 复用已有项目角色 -->
      <div v-if="existingProjects.length" class="form-section">
        <label>复用已有项目角色（可选）</label>
        <p class="text-xs text-dim" style="margin-bottom:8px">如果新内容和某个已有项目是同一个故事，可以复用角色三视图，保持人物外观一致</p>
        <select v-model="importFrom" class="select-input">
          <option value="">不复用，重新生成角色</option>
          <option v-for="p in existingProjects" :key="p.id" :value="p.id">
            {{ p.name }} ({{ p.id }})
          </option>
        </select>
      </div>

      <div class="form-actions">
        <button
          class="btn btn-primary"
          :disabled="!name.trim() || !novelText.trim() || submitting"
          @click="submit"
        >
          {{ submitting ? '创建中...' : '开始创作' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createProject, getProjects, importCharacters } from '../api'

const router = useRouter()
const name = ref('')
const novelText = ref('')
const submitting = ref(false)
const existingProjects = ref([])
const importFrom = ref('')

onMounted(async () => {
  try {
    const { data } = await getProjects()
    existingProjects.value = data.filter(p => p.status !== 'created')
  } catch (e) {}
})

const submit = async () => {
  submitting.value = true
  try {
    const { data } = await createProject({ name: name.value.trim(), novel_text: novelText.value.trim() })
    const newId = data.project_id

    // 如果选择了复用角色
    if (importFrom.value) {
      try {
        await importCharacters(newId, importFrom.value)
      } catch (e) {
        console.error('导入角色失败:', e)
      }
    }

    router.push(`/project/${newId}`)
  } catch (e) {
    alert('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-card {
  max-width: 720px;
}

.form-section {
  margin-bottom: 24px;
}

.char-count {
  margin-top: 6px;
  text-align: right;
  font-size: 12px;
  color: var(--text-light);
}

.count-warn { color: var(--warning); }

.form-actions {
  padding-top: 8px;
}

.select-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 14px;
  font-family: var(--font-body);
  cursor: pointer;
}
.select-input:focus {
  outline: none;
  border-color: var(--primary);
}
</style>
