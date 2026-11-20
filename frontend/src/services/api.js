// All calls to the backend go through this file,
// so the backend address lives in exactly one place.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Turns { search: 'x', severity: '' } into "?search=x" (empty values are left out)
function queryString(params = {}) {
  const query = new URLSearchParams()
  for (const [name, value] of Object.entries(params)) {
    if (value !== '' && value !== null && value !== undefined) query.set(name, value)
  }
  const text = query.toString()
  return text ? `?${text}` : ''
}

// Sends one request and returns the JSON reply, or throws a readable error.
async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    // A refused parameter comes back as a list: "limit: Input should be ≥ 1"
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((item) => `${item.loc?.slice(-1)[0]}: ${item.msg}`).join('; ')
      : typeof body?.detail === 'string'
        ? body.detail
        : null
    throw new Error(detail || `Request failed with status ${response.status}`)
  }
  return response.json()
}

function postJson(path, data) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// ---------- Health and projects ----------

export function getHealth() {
  return request('/health')
}

export function getProjects() {
  return request('/projects')
}

// ---------- Logs ----------

// filters: { search, severity, min_severity, service, error_type, request_id, trace_id,
//            incident_id, since, until, project_id } plus { order, limit, offset }
export function getLogs(filters = {}) {
  return request(`/logs${queryString(filters)}`)
}

// How many logs match the same filters (for paging)
export function countLogs(filters = {}) {
  return request(`/logs/count${queryString(filters)}`)
}

export function getLogStats(projectId) {
  return request(`/logs/stats${queryString({ project_id: projectId })}`)
}

// minutes: only the last few minutes (used while a live stream runs)
export function getTimeline(projectId, minutes) {
  return request(`/logs/timeline${queryString({ project_id: projectId, minutes, slots: 32 })}`)
}

export function submitStructuredLog(log, projectId) {
  return postJson('/logs', { ...log, project_id: projectId })
}

export function submitLogText(text, projectId) {
  return postJson('/logs/text', { text, project_id: projectId })
}

export function uploadLogFile(file, projectId) {
  const form = new FormData()
  form.append('file', file)
  if (projectId) form.append('project_id', projectId)
  return request('/logs/upload', { method: 'POST', body: form })
}

// A plain link: downloads the stored logs (with the same filters) as a CSV file
export function exportLogsUrl(filters) {
  return `${API_URL}/logs/export${queryString(filters)}`
}

export function deleteLog(id) {
  return request(`/logs/${id}`, { method: 'DELETE' })
}

export function deleteAllLogs(projectId) {
  return request(`/logs${queryString({ project_id: projectId })}`, { method: 'DELETE' })
}

// ---------- Incidents ----------

// status: OPEN, RESOLVED or ALL. filters: { min_severity, service, limit, offset }
export function getIncidents(projectId, status = 'OPEN', filters = {}) {
  return request(`/incidents${queryString({ project_id: projectId, status, ...filters })}`)
}

export function getIncidentSummary(projectId) {
  return request(`/incidents/summary${queryString({ project_id: projectId })}`)
}

export function getIncident(id) {
  return request(`/incidents/${id}`)
}

export function setIncidentStatus(id, status) {
  return request(`/incidents/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

// engine: auto, llm or rules
export function diagnoseIncident(id, engine = 'auto') {
  return request(`/incidents/${id}/diagnose${queryString({ engine })}`, { method: 'POST' })
}

export function getDiagnoses(id) {
  return request(`/incidents/${id}/diagnoses`)
}

export function detectIncidents(projectId) {
  return request(`/incidents/detect${queryString({ project_id: projectId })}`, { method: 'POST' })
}

// ---------- Service monitoring (the demo shop) ----------

export function getMonitor() {
  return request('/monitor')
}

export function startAllServices() {
  return request('/monitor/start-all', { method: 'POST' })
}

export function stopAllServices() {
  return request('/monitor/stop-all', { method: 'POST' })
}

// action: start, stop or restart. fault (restart of shop-api only): '', crash, slow, bad-config
export function controlService(name, action, fault) {
  return request(`/monitor/services/${name}/${action}${queryString({ fault })}`, { method: 'POST' })
}

export function runScenario(key) {
  return request(`/monitor/scenarios/${key}`, { method: 'POST' })
}

// ---------- Real-world datasets and live streaming ----------

export function getDatasets() {
  return request('/datasets')
}

// One dataset's facts plus a page of its lines: { search, offset, limit }
export function getDataset(key, params) {
  return request(`/datasets/${key}${queryString(params)}`)
}

// A plain link, so the browser downloads the original file
export function datasetDownloadUrl(key) {
  return `${API_URL}/datasets/${key}/download`
}

// One page of Loghub's official CSV for a dataset: { search, offset, limit }
export function getDatasetCsv(key, params) {
  return request(`/datasets/${key}/csv${queryString(params)}`)
}

export function datasetCsvUrl(key) {
  return `${API_URL}/datasets/${key}/csv/download`
}

export function parsedCsvUrl(key) {
  return `${API_URL}/datasets/${key}/parsed.csv`
}

export function importDataset(key) {
  return request(`/datasets/${key}/import`, { method: 'POST' })
}

export function getStreamStatus() {
  return request('/datasets/stream')
}

export function startStream(key, speed) {
  return request(`/datasets/${key}/stream${queryString({ speed })}`, { method: 'POST' })
}

export function stopStream() {
  return request('/datasets/stream/stop', { method: 'POST' })
}

// ---------- Telemetry (OpenTelemetry) ----------

export function getTelemetryServices(params) {
  return request(`/telemetry/services${queryString(params)}`)
}

export function getMetricNames(params) {
  return request(`/telemetry/metrics${queryString(params)}`)
}

// { metric, project_id, service, window_minutes, step_seconds, aggregation }
export function getMetricSeries(params) {
  return request(`/telemetry/series${queryString(params)}`)
}

// { project_id, service, status, min_duration_ms, window_minutes, limit }
export function getTraces(params) {
  return request(`/telemetry/traces${queryString(params)}`)
}

export function getTrace(traceId) {
  return request(`/telemetry/traces/${traceId}`)
}

// ---------- Investigation tools ----------

export function getTools() {
  return request('/tools')
}

export function getAiConfig() {
  return request('/tools/config')
}

export function runTool(name, parameters) {
  return postJson(`/tools/${name}`, parameters)
}
