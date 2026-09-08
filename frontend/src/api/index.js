import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
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

// 生成流程
export const generateAll = (id) => api.post(`/projects/${id}/generate-all`)
export const stopProject = (id) => api.post(`/projects/${id}/stop`)
export const importCharacters = (targetId, sourceId) => api.post(`/projects/${targetId}/import-characters/${sourceId}`)
export const generateScript = (id) => api.post(`/projects/${id}/generate-script`)
export const generateCharacters = (id) => api.post(`/projects/${id}/generate-characters`)
export const generateShots = (id) => api.post(`/projects/${id}/generate-shots`)
export const generateAudio = (id) => api.post(`/projects/${id}/generate-audio`)
export const generateVideos = (id) => api.post(`/projects/${id}/generate-videos`)
export const composeVideo = (id) => api.post(`/projects/${id}/compose`)

// 成本 / 质量 / 单镜重做
export const getBudget = (id) => api.get(`/projects/${id}/budget`)
export const redoSingleShot = (id, index) => api.post(`/projects/${id}/shot/${index}/redo`)
export const getTaskStatus = (id) => api.get(`/projects/${id}/task`)

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
