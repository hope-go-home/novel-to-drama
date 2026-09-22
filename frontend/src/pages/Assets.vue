<template>
  <div class="assets fade-in">
    <div class="header">
      <div>
        <h1>素材库</h1>
        <p class="text-dim text-sm" style="margin-top:4px">管理音效 / 环境音 / BGM，配置中文名映射与音量</p>
      </div>
    </div>

    <!-- 分类切换 -->
    <div class="tabs">
      <button
        v-for="c in categories" :key="c.key"
        class="tab" :class="{ active: category === c.key }"
        @click="switchCategory(c.key)"
      >{{ c.label }}（{{ counts[c.key] ?? '…' }}）</button>
    </div>

    <!-- 上传 -->
    <div class="upload-box">
      <input ref="fileInput" type="file" accept="audio/*" @change="onFileChange" />
      <input v-model="uploadName" class="input" placeholder="中文名（多个用逗号分隔）" />
      <button class="btn btn-primary btn-sm" :disabled="!uploadFile || uploading" @click="doUpload">
        {{ uploading ? '上传中…' : '上传' }}
      </button>
    </div>

    <!-- 搜索 -->
    <div class="search-box">
      <input v-model="search" class="input" placeholder="搜索名称 / 文件名" />
    </div>

    <div v-if="loading" class="text-center text-dim" style="padding:40px 0">加载中…</div>

    <!-- 文件列表 -->
    <div v-else class="asset-list">
      <div v-for="f in filteredFiles" :key="f.filename" class="asset-row">
        <div class="asset-main">
          <div class="asset-file">{{ f.filename }}</div>
          <div class="asset-names">
            <template v-if="!editing[f.filename]">
              <span v-for="n in f.names" :key="n" class="name-tag">{{ n }}</span>
              <span v-if="!f.names.length" class="text-dim text-xs">（未登记中文名）</span>
            </template>
            <template v-else>
              <input v-model="editText[f.filename]" class="input input-sm" placeholder="中文名，逗号分隔" />
            </template>
          </div>
        </div>
        <div class="asset-actions">
          <audio controls :src="f.url" preload="none" />
          <template v-if="!editing[f.filename]">
            <button class="btn btn-outline btn-xs" @click="startEdit(f)">改名字</button>
          </template>
          <template v-else>
            <button class="btn btn-primary btn-xs" @click="saveEdit(f)">保存</button>
            <button class="btn btn-ghost btn-xs" @click="editing[f.filename] = false">取消</button>
          </template>
          <button class="btn btn-danger btn-xs" @click="remove(f)">删除</button>
        </div>
      </div>
      <div v-if="!filteredFiles.length" class="text-center text-dim" style="padding:30px 0">没有素材</div>
    </div>

    <!-- 音效音量（仅音效分类） -->
    <section v-if="category === 'sfx'" class="vol-section">
      <h2 class="section-title">音效音量倍率</h2>
      <p class="text-dim text-xs" style="margin:6px 0 10px">按音效名（支持子串）调音量，1.0=不变，越小越轻</p>
      <div v-for="(row, i) in volRows" :key="i" class="vol-row">
        <input v-model="row.name" class="input input-sm" placeholder="音效名" />
        <input v-model="row.value" class="input input-sm vol-num" placeholder="0.5" />
        <button class="btn btn-danger btn-xs" @click="volRows.splice(i, 1)">删</button>
      </div>
      <div class="vol-actions">
        <button class="btn btn-outline btn-xs" @click="volRows.push({ name: '', value: '' })">加一条</button>
        <button class="btn btn-primary btn-xs" :disabled="savingVol" @click="saveVol">保存音量</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getAssets, uploadAsset, updateAssetNames, deleteAsset, getSfxVol, updateSfxVol } from '../api'

const categories = [
  { key: 'sfx', label: '音效' },
  { key: 'ambience', label: '环境音' },
  { key: 'bgm', label: 'BGM' },
]

const category = ref('sfx')
const files = ref([])
const counts = ref({})
const loading = ref(true)
const search = ref('')
const uploading = ref(false)
const uploadFile = ref(null)
const uploadName = ref('')
const fileInput = ref(null)
const editing = ref({})
const editText = ref({})
const volRows = ref([])
const savingVol = ref(false)

const filteredFiles = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return files.value
  return files.value.filter(f =>
    f.filename.toLowerCase().includes(q) || f.names.some(n => n.toLowerCase().includes(q))
  )
})

const load = async () => {
  loading.value = true
  try {
    const { data } = await getAssets(category.value)
    files.value = data.files || []
    counts.value[category.value] = data.count
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const loadCounts = async () => {
  for (const c of categories) {
    try {
      const { data } = await getAssets(c.key)
      counts.value[c.key] = data.count
    } catch (e) {}
  }
}

const switchCategory = async (key) => {
  category.value = key
  editing.value = {}
  search.value = ''
  await load()
  if (key === 'sfx') await loadVol()
}

const onFileChange = (e) => {
  uploadFile.value = e.target.files?.[0] || null
}

const doUpload = async () => {
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', uploadFile.value)
    fd.append('name', uploadName.value)
    await uploadAsset(category.value, fd)
    uploadFile.value = null
    uploadName.value = ''
    if (fileInput.value) fileInput.value.value = ''
    await load()
    await loadCounts()
  } catch (e) {
    alert('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

const startEdit = (f) => {
  editing.value[f.filename] = true
  editText.value[f.filename] = (f.names || []).join('，')
}

const saveEdit = async (f) => {
  const names = (editText.value[f.filename] || '')
    .split(/[，,]/).map(s => s.trim()).filter(Boolean)
  try {
    await updateAssetNames(category.value, f.filename, names)
    editing.value[f.filename] = false
    await load()
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

const remove = async (f) => {
  if (!confirm(`确定删除「${f.filename}」？`)) return
  try {
    await deleteAsset(category.value, f.filename)
    await load()
    await loadCounts()
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

const loadVol = async () => {
  try {
    const { data } = await getSfxVol()
    volRows.value = Object.entries(data || {})
      .filter(([k]) => !k.startsWith('_'))
      .map(([k, v]) => ({ name: k, value: String(v) }))
  } catch (e) {}
}

const saveVol = async () => {
  savingVol.value = true
  try {
    const body = {}
    for (const r of volRows.value) {
      if (r.name && r.name.trim() && r.value !== '') body[r.name.trim()] = Number(r.value)
    }
    await updateSfxVol(body)
    await loadVol()
    alert('已保存')
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingVol.value = false
  }
}

onMounted(async () => {
  await load()
  await loadCounts()
  await loadVol()
})
</script>

<style scoped>
.header { margin-bottom: 16px; }
h1 { font-family: var(--font-display); font-size: 22px; }

.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tab {
  background: none; border: 1px solid var(--border); color: var(--text-dim);
  padding: 6px 14px; border-radius: var(--radius); cursor: pointer; font-size: 13px;
  transition: all 0.15s;
}
.tab:hover { color: var(--text); }
.tab.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.upload-box, .search-box {
  display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;
}
.input {
  flex: 1; min-width: 160px; padding: 7px 10px; font-size: 13px;
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text);
}
.input-sm { padding: 4px 8px; font-size: 12px; }
.input:focus { outline: none; border-color: var(--primary); }

.asset-list { display: flex; flex-direction: column; }
.asset-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 0; border-bottom: 1px solid var(--border);
}
.asset-row:last-child { border-bottom: none; }
.asset-main { flex: 1; min-width: 0; }
.asset-file { font-size: 13px; word-break: break-all; }
.asset-names { margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.name-tag {
  font-size: 11px; background: var(--bg-hover); border-radius: 4px; padding: 1px 6px; color: var(--text-dim);
}
.asset-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.asset-actions audio { height: 30px; }

.vol-section { margin-top: 28px; border-top: 1px solid var(--border); padding-top: 16px; }
.section-title { font-family: var(--font-display); font-size: 15px; }
.vol-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.vol-num { max-width: 90px; }
.vol-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
