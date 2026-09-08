import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// AI 改写剧本需生成完整 JSON + 可能多轮重试（对齐后端 LLM 300s 超时）
const slow = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

// 项目
export const getProjects = () => api.get('/projects')
export const createProject = (data) => api.post('/projects', data)
export const getProject = (id) => api.get(`/projects/${id}`)
export const deleteProject = (id) => api.delete(`/projects/${id}`)
export const getResult = (id) => api.get(`/projects/${id}/result`)
export const updateProjectSettings = (id, data) => api.post(`/projects/${id}/settings`, data)

// 日志
export const getLogs = (limit = 100, projectId = '') => api.get('/logs', { params: { limit, project_id: projectId } })
export const clearLogs = () => api.delete('/logs')

// 生成流程（force=true 表示用户已确认超预算继续）
const withForce = (force) => (force ? { force: true } : {})
export const generateAll = (id, force) => api.post(`/projects/${id}/generate-all`, null, { params: withForce(force) })
export const stopProject = (id) => api.post(`/projects/${id}/stop`)
export const importCharacters = (targetId, sourceId) => api.post(`/projects/${targetId}/import-characters/${sourceId}`)
export const generateScript = (id, force) => api.post(`/projects/${id}/generate-script`, null, { params: withForce(force) })
export const generateCharacters = (id, force) => api.post(`/projects/${id}/generate-characters`, null, { params: withForce(force) })
export const generateShots = (id, force) => api.post(`/projects/${id}/generate-shots`, null, { params: withForce(force) })
export const generateAudio = (id, force) => api.post(`/projects/${id}/generate-audio`, null, { params: withForce(force) })
export const generateVideos = (id, force) => api.post(`/projects/${id}/generate-videos`, null, { params: withForce(force) })
export const composeVideo = (id, force) => api.post(`/projects/${id}/compose`, null, { params: withForce(force) })

// 成本 / 质量 / 单镜重做
export const getBudget = (id) => api.get(`/projects/${id}/budget`)
export const redoSingleShot = (id, index, force) => api.post(`/projects/${id}/shot/${index}/redo`, null, { params: withForce(force) })
export const getTaskStatus = (id) => api.get(`/projects/${id}/task`)

// AI 剧本助手
export const aiChatScript = (id, instruction, force) => slow.post(`/projects/${id}/chat`, { instruction, force })
export const applyScript = (id, script) => slow.post(`/projects/${id}/script/apply`, { script })

// 删除资产
export const deleteScript = (id) => api.delete(`/projects/${id}/script`)
export const deleteCharacters = (id) => api.delete(`/projects/${id}/characters`)
export const deleteShots = (id) => api.delete(`/projects/${id}/shots`)
export const deleteAudio = (id) => api.delete(`/projects/${id}/audio`)
export const deleteVideos = (id) => api.delete(`/projects/${id}/videos`)
export const deleteOutput = (id) => api.delete(`/projects/${id}/output`)
export const deleteSingleShot = (id, index) => api.delete(`/projects/${id}/shot/${index}`)
export const deleteSingleVideo = (id, index) => api.delete(`/projects/${id}/video/${index}`)

export default api
