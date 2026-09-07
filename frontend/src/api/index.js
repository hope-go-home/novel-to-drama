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

export default api
