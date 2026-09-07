<template>
  <div class="log-panel">
    <div class="log-header">
      <h3>运行日志</h3>
      <div class="log-actions">
        <button class="btn btn-ghost btn-xs" @click="$emit('clear')">清空</button>
        <button class="btn btn-ghost btn-xs" @click="$emit('refresh')">刷新</button>
      </div>
    </div>
    <div class="log-list" ref="logList">
      <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
      <div v-for="(log, i) in logs" :key="i" :class="['log-item', `log-${log.level}`]">
        <span class="log-time">{{ log.time?.slice(11) }}</span>
        <span class="log-level">{{ levelIcon(log.level) }}</span>
        <span class="log-module">{{ log.module }}</span>
        <span class="log-msg">{{ log.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({ logs: { type: Array, default: () => [] } })
defineEmits(['clear', 'refresh'])

const logList = ref(null)

const levelIcon = (level) => {
  return { INFO: 'ℹ️', WARN: '⚠️', ERROR: '❌', SUCCESS: '✅' }[level] || '📋'
}

watch(() => props.logs.length, async () => {
  await nextTick()
  if (logList.value) {
    logList.value.scrollTop = logList.value.scrollHeight
  }
})
</script>

<style scoped>
.log-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-hover);
}
.log-header h3 { font-size: 14px; font-weight: 600; }
.log-actions { display: flex; gap: 4px; }

.log-list {
  max-height: 240px;
  overflow-y: auto;
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
}

.log-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-light);
}

.log-item {
  display: flex;
  gap: 8px;
  padding: 4px 16px;
  border-bottom: 1px solid var(--border);
  align-items: baseline;
}
.log-item:last-child { border-bottom: none; }

.log-time { color: var(--text-light); flex-shrink: 0; width: 60px; }
.log-level { flex-shrink: 0; width: 16px; text-align: center; }
.log-module {
  flex-shrink: 0;
  width: 60px;
  font-weight: 600;
  color: var(--text-dim);
}
.log-msg { flex: 1; word-break: break-all; }

.log-ERROR { background: #FEF2F2; }
.log-ERROR .log-msg { color: var(--error); }
.log-SUCCESS .log-msg { color: var(--success); }
.log-WARN .log-msg { color: var(--warning); }
</style>
